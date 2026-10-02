"""Asynchronous chat coordination shared by local web clients."""

from __future__ import annotations

import contextlib
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.agent_modes import get_mode, is_conversational_greeting, resolve_mode
from core.chat_attachments import AttachmentStore, StoredAttachment, prepare_prompt_attachments
from core.chat_outputs import OutputAttachmentStore, collect_outputs
from core.conversations import ConversationManager, get_conversation_manager


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatBusyError(RuntimeError):
    pass


class ChatNotFoundError(LookupError):
    pass


class ChatCancelled(BaseException):
    """Internal cooperative cancellation signal that bypasses model Exception handlers."""


@dataclass
class ChatJob:
    id: str
    conversation_id: str
    user_message_id: str
    attachment_ids: list[str]
    agent_mode: str = ""
    work_agents: list[str] = field(default_factory=list)
    status: str = "queued"
    created_at: str = field(default_factory=_now_iso)
    started_at: str = ""
    completed_at: str = ""
    response: str = ""
    error: str = ""
    chunk_count: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Future | None = field(default=None, repr=False)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_message_id": self.user_message_id,
            "status": self.status,
            "agent_mode": self.agent_mode,
            "work_agents": self.work_agents,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "response": self.response,
            "error": self.error,
            "chunk_count": self.chunk_count,
            # Lets the polling fallback deliver generated files too, not just SSE.
            "attachments": self.attachments,
        }


Responder = Callable[..., str]


class ChatCoordinator:
    """Run one native inference at a time and publish its lifecycle as events."""

    _VALID_CONVERSATION_ID = re.compile(r"^[a-f0-9]{12}$")
    _TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

    def __init__(
        self,
        *,
        settings,
        event_hub,
        conversation_manager: ConversationManager | None = None,
        attachment_store: AttachmentStore | None = None,
        responder: Responder | None = None,
        image_responder: Responder | None = None,
        ensure_model_ready: Callable | None = None,
        memory_service=None,
    ):
        self.settings = settings
        self.event_hub = event_hub
        self.conversations = conversation_manager or get_conversation_manager(
            Path(settings.data_dir) / "conversations"
        )
        self.attachments = attachment_store or AttachmentStore(
            Path(settings.data_dir) / "web_uploads",
            allowed_extensions=settings.all_extensions,
            max_size_mb=settings.max_file_size_mb,
        )
        # Generated files are kept after the turn so the user can still download
        # them from the conversation, unlike the temporary uploads above.
        self.outputs = OutputAttachmentStore(
            root=Path(settings.data_dir) / "chat_outputs",
            allowed_extensions=set(settings.all_extensions),
            max_bytes=max(1, int(settings.max_file_size_mb)) * 1024 * 1024,
        )
        self._responder = responder or self._default_responder
        self._image_responder = image_responder or self._default_image_responder
        self._ensure_model_ready_callback = ensure_model_ready or self._ensure_model_ready
        self.memory_service = memory_service
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CelsiusWebChat")
        self._jobs: dict[str, ChatJob] = {}
        self._active_job_id = ""
        self._lock = threading.RLock()

    def submit(
        self,
        *,
        message: str,
        conversation_id: str = "",
        attachment_ids: list[str] | None = None,
        model_id: str = "",
        agent_mode: str = "",
        work_agents: list[str] | None = None,
        source: str = "web",
    ) -> dict[str, Any]:
        clean_message = (message or "").strip()
        if not clean_message:
            raise ValueError("A mensagem nao pode estar vazia.")
        attachment_ids = list(dict.fromkeys(attachment_ids or []))
        if len(attachment_ids) > 10:
            raise ValueError("Envie no maximo 10 anexos por mensagem.")
        stored_attachments = self.attachments.resolve(attachment_ids)
        # Older Work clients prefix every turn, including greetings, with TAREFA.
        # Normalize at the shared boundary so desktop, phone and WhatsApp agree.
        if not stored_attachments and is_conversational_greeting(clean_message):
            clean_message = re.sub(r"^TAREFA\s*:\s*", "", clean_message, flags=re.I)
            agent_mode = "assistente"
            work_agents = []
        # An unknown mode falls back to the default instead of failing the turn.
        mode = get_mode(agent_mode or self.settings.agent.default_mode)
        if not self.settings.agent.enabled:
            mode = get_mode(None)
        elif not is_conversational_greeting(clean_message):
            # Route the turn to the lane that actually fits it. The router keeps
            # an explicitly chosen non-default mode and any "modo X" command, so
            # this only ever upgrades the default lane. A pure greeting stays on
            # the assistant instead of being classified into a specialist.
            mode = get_mode(resolve_mode(clean_message, requested=mode.id))

        with self._lock:
            active = self._jobs.get(self._active_job_id)
            if active and active.status not in self._TERMINAL_STATUSES:
                raise ChatBusyError(
                    "O Celsius ainda esta respondendo. Aguarde ou cancele a resposta atual."
                )

            conversation = self._resolve_conversation(conversation_id)
            history = self._history(conversation)
            attachment_metadata = [item.public_dict() for item in stored_attachments]
            user_message = self.conversations.add_message(
                conversation["id"],
                "user",
                clean_message,
                metadata={
                    "attachments": attachment_metadata,
                    "source": (source or "web").strip().lower(),
                    "agent_mode": mode.id,
                },
            )
            job = ChatJob(
                id=uuid.uuid4().hex,
                conversation_id=conversation["id"],
                user_message_id=user_message["id"],
                attachment_ids=attachment_ids,
                agent_mode=mode.id,
                work_agents=work_agents or [],
            )
            self._jobs[job.id] = job
            self._active_job_id = job.id
            self._prune_jobs()
            self.event_hub.publish(
                "chat.accepted",
                {
                    "job_id": job.id,
                    "conversation_id": job.conversation_id,
                    "message": user_message,
                },
            )
            job.future = self._executor.submit(
                self._run,
                job,
                clean_message,
                history,
                stored_attachments,
                model_id,
            )

        return job.public_dict()

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ChatNotFoundError("Tarefa de chat nao encontrada.")
            return job.public_dict()

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ChatNotFoundError("Tarefa de chat nao encontrada.")
            if job.status in self._TERMINAL_STATUSES:
                return job.public_dict()
            job.cancel_event.set()
            if job.future and job.future.cancel():
                self._finish_cancelled(job)
            else:
                job.status = "cancelling"
                self.event_hub.publish("chat.cancelling", {"job_id": job.id})
            return job.public_dict()

    def list_conversations(self) -> list[dict[str, Any]]:
        return sorted(
            self.conversations.list(),
            key=lambda item: item.get("updated_at", ""),
            reverse=True,
        )

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        if not self._VALID_CONVERSATION_ID.fullmatch(conversation_id or ""):
            raise ChatNotFoundError("Conversa nao encontrada.")
        conversation = self.conversations.load(conversation_id)
        if conversation is None:
            raise ChatNotFoundError("Conversa nao encontrada.")
        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        if not self._VALID_CONVERSATION_ID.fullmatch(conversation_id or ""):
            raise ChatNotFoundError("Conversa nao encontrada.")
        with self._lock:
            active = self._jobs.get(self._active_job_id)
            if (
                active
                and active.status not in self._TERMINAL_STATUSES
                and active.conversation_id == conversation_id
            ):
                raise ChatBusyError("Interrompa a resposta atual antes de excluir esta conversa.")
            if self.conversations.load(conversation_id) is None:
                raise ChatNotFoundError("Conversa nao encontrada.")
            deleted = self.conversations.delete(conversation_id)
        if deleted:
            with contextlib.suppress(Exception):
                if self.memory_service is None:
                    from core.memory import get_memory_service

                    memory_service = get_memory_service()
                else:
                    memory_service = self.memory_service
                delete_for_conversation = getattr(memory_service, "delete_for_conversation", None)
                if delete_for_conversation is not None:
                    delete_for_conversation(conversation_id)
            self.event_hub.publish(
                "conversation.deleted",
                {"conversation_id": conversation_id},
            )
        return deleted

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                if job.status not in self._TERMINAL_STATUSES:
                    job.cancel_event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _resolve_conversation(self, conversation_id: str) -> dict[str, Any]:
        if not conversation_id:
            return self.conversations.create()
        return self.get_conversation(conversation_id)

    @staticmethod
    def _history(conversation: dict[str, Any], max_messages: int = 40) -> list[dict[str, str]]:
        history = []
        for message in conversation.get("messages", [])[-max_messages:]:
            role = message.get("role")
            content = str(message.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                history.append({"role": role, "content": content})
        return history

    def _run(
        self,
        job: ChatJob,
        message: str,
        history: list[dict[str, str]],
        attachments: list[StoredAttachment],
        model_id: str,
    ) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = _now_iso()
        self.event_hub.publish(
            "chat.started",
            {"job_id": job.id, "conversation_id": job.conversation_id},
        )

        def check_cancelled() -> None:
            if job.cancel_event.is_set():
                raise ChatCancelled()

        def on_status(text: str) -> None:
            check_cancelled()
            self.event_hub.publish("chat.status", {"job_id": job.id, "text": text})

        def on_chunk(chunk: str) -> None:
            if chunk:
                with self._lock:
                    job.response += chunk
                    job.chunk_count += 1
                    sequence = job.chunk_count
                self.event_hub.publish(
                    "chat.chunk",
                    {"job_id": job.id, "sequence": sequence, "text": chunk},
                )
            check_cancelled()

        try:
            check_cancelled()
            self._ensure_model_ready_callback(on_status)
            memories = self._load_memories(message, on_status, job.conversation_id)
            prompt = {
                "pergunta": message,
                "documento": "",
                "nome_documento": "",
                "memorias_relevantes": memories,
                "anexos": [(str(item.path), item.name) for item in attachments],
                "modelo_solicitado": model_id or self.settings.llm_model,
                "system_prompt": self._system_prompt(),
                "historico": history,
                "approval_scope": job.conversation_id,
                "agent_mode": job.agent_mode or self.settings.agent.default_mode,
                "work_agents": job.work_agents,
            }
            prepare_prompt_attachments(prompt, settings=self.settings, fn_status=on_status)
            check_cancelled()
            from ai.task_runtime import is_task_command

            # Files the agent generates inside this block are offered to the user
            # as downloadable attachments on the reply. The job points at the
            # same list so an interrupted turn keeps whatever was already made.
            with collect_outputs(self.outputs) as produced:
                with self._lock:
                    job.attachments = produced
                if job.work_agents and len(job.work_agents) >= 2:
                    from ai.multi_agent import run_multi_agent_work

                    response = run_multi_agent_work(
                        prompt,
                        self._responder,
                        data_dir=self.settings.data_dir,
                        fn_status=on_status,
                        fn_chunk=on_chunk,
                        should_cancel=job.cancel_event.is_set,
                    )
                elif prompt.get("caminho_imagem") and not is_task_command(message):
                    response = self._image_responder(
                        prompt["caminho_imagem"],
                        message,
                        fn_status=on_status,
                        fn_chunk=on_chunk,
                    )
                else:
                    response = self._responder(
                        prompt,
                        fn_status=on_status,
                        fn_passo=None,
                        fn_chunk=on_chunk,
                    )
            check_cancelled()
            response = str(response or "").strip()
            # A completed job guarantees that its temporary uploads are gone.
            self.attachments.discard(job.attachment_ids)
            metadata: dict[str, Any] = {"source": "web", "job_id": job.id}
            if produced:
                metadata["attachments"] = produced
            assistant_message = self.conversations.add_message(
                job.conversation_id,
                "assistant",
                response,
                metadata=metadata,
            )
            self._kick_memory_extraction(job.conversation_id)
            with self._lock:
                job.status = "completed"
                job.completed_at = _now_iso()
                job.response = response
            self.event_hub.publish(
                "chat.completed",
                {
                    "job_id": job.id,
                    "conversation_id": job.conversation_id,
                    "message": assistant_message,
                    "text": response,
                    "attachments": produced,
                },
            )
        except ChatCancelled:
            self._finish_cancelled(job)
        except BaseException as exc:
            with self._lock:
                job.status = "failed"
                job.completed_at = _now_iso()
                job.error = str(exc)
            self.event_hub.publish(
                "chat.failed",
                {"job_id": job.id, "error": str(exc)},
            )
        finally:
            self.attachments.discard(job.attachment_ids)
            with self._lock:
                if self._active_job_id == job.id:
                    self._active_job_id = ""

    def _finish_cancelled(self, job: ChatJob) -> None:
        from ai.interruption import marcar_interrompida

        with self._lock:
            job.status = "cancelled"
            job.completed_at = _now_iso()
            partial = str(job.response or "")
            if self._active_job_id == job.id:
                self._active_job_id = ""
        self.attachments.discard(job.attachment_ids)
        payload: dict[str, Any] = {"job_id": job.id, "attachments": job.attachments}
        if partial.strip():
            text = marcar_interrompida(partial)
            job.response = text
            metadata: dict[str, Any] = {
                "source": "web",
                "job_id": job.id,
                "interrupted": True,
            }
            # A file produced before the interruption is still worth keeping.
            if job.attachments:
                metadata["attachments"] = job.attachments
            assistant_message = self.conversations.add_message(
                job.conversation_id,
                "assistant",
                text,
                metadata=metadata,
            )
            payload.update(
                {
                    "conversation_id": job.conversation_id,
                    "message": assistant_message,
                    "text": text,
                }
            )
        self.event_hub.publish("chat.cancelled", payload)

    def _load_memories(
        self,
        message: str,
        on_status: Callable[[str], None],
        conversation_id: str = "",
    ) -> list[str]:
        if not self.settings.features.memory:
            return []
        if self.memory_service is None:
            from core.memory import get_memory_service

            self.memory_service = get_memory_service()
        from core.memory import memory_query_context

        user_messages = [message]
        if conversation_id:
            conversation = self.conversations.load(conversation_id)
            if conversation:
                user_messages.extend(
                    str(item["content"])
                    for item in conversation.get("messages", [])
                    if item.get("role") == "user" and item.get("content")
                )
        queries = memory_query_context(user_messages)
        search_multi = getattr(self.memory_service, "search_multi", None)
        if search_multi is not None:
            memories = search_multi(queries)
        else:
            memories = []
            seen: set[str] = set()
            for query in queries:
                for match in self.memory_service.search(query) or []:
                    if match not in seen:
                        seen.add(match)
                        memories.append(match)
        if memories:
            on_status("Aplicando contexto pessoal relevante...")
        return memories

    def _kick_memory_extraction(self, conversation_id: str) -> None:
        """Learn durable user facts from the finished turn, in background."""
        settings = self.settings
        if not settings.features.memory or not settings.memory.auto_extract_facts:
            return
        conversation = self.conversations.load(conversation_id)
        if not conversation:
            return
        messages = [
            {"role": item.get("role"), "content": item.get("content")}
            for item in conversation.get("messages", [])
            if item.get("role") in {"user", "assistant"} and item.get("content")
        ][-(settings.memory.extraction_recent_messages or 10) :]
        if not messages:
            return
        from core.memory import extract_and_store_async

        extract_and_store_async(messages, conversation_id=conversation_id)

    def _system_prompt(self) -> str:
        return (
            f"Voce e {self.settings.assistant.name}, {self.settings.assistant.profile}. "
            "Sua identidade fixa e Celsius. Responda em portugues do Brasil. "
            "O perfil da empresa orienta o contexto, mas nao limita os assuntos."
        )

    def _ensure_model_ready(self, on_status: Callable[[str], None]) -> None:
        from core.llama_cpp import get_llama_manager
        from core.model_router import model_start_kwargs

        manager = get_llama_manager()
        if manager.is_healthy():
            return
        model_path = self.settings.get_model_path(self.settings.llm_model)
        if not model_path.is_file():
            raise FileNotFoundError(f"Modelo local nao encontrado: {model_path}")
        on_status("Carregando modelo local...")
        start_kwargs = model_start_kwargs(self.settings.llm_model)
        started = manager.start(
            model_id=self.settings.llm_model,
            n_gpu_layers=start_kwargs.get("n_gpu_layers", self.settings.model.n_gpu_layers),
            n_ctx=start_kwargs.get("n_ctx", self.settings.model.num_ctx),
            n_batch=self.settings.model.n_batch,
            n_threads=self.settings.model.n_threads,
            use_mmap=self.settings.model.use_mmap,
            use_mlock=self.settings.model.use_mlock,
        )
        if not started:
            raise RuntimeError("Nao foi possivel iniciar o modelo local.")

    @staticmethod
    def _default_responder(*args, **kwargs) -> str:
        from ai.engine import gerar_resposta

        return gerar_resposta(*args, **kwargs)

    @staticmethod
    def _default_image_responder(*args, **kwargs) -> str:
        from ai.engine import gerar_resposta_com_imagem

        return gerar_resposta_com_imagem(*args, **kwargs)

    def _prune_jobs(self) -> None:
        if len(self._jobs) <= 200:
            return
        terminal_ids = [
            job_id for job_id, job in self._jobs.items() if job.status in self._TERMINAL_STATUSES
        ]
        for job_id in terminal_ids[: len(self._jobs) - 200]:
            self._jobs.pop(job_id, None)
