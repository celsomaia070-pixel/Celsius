"""Asynchronous chat coordination shared by local web clients."""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.chat_attachments import AttachmentStore, StoredAttachment, prepare_prompt_attachments
from core.conversations import ConversationManager, get_conversation_manager


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
    status: str = "queued"
    created_at: str = field(default_factory=_now_iso)
    started_at: str = ""
    completed_at: str = ""
    response: str = ""
    error: str = ""
    chunk_count: int = 0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Future | None = field(default=None, repr=False)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "user_message_id": self.user_message_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "response": self.response,
            "error": self.error,
            "chunk_count": self.chunk_count,
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
    ) -> dict[str, Any]:
        clean_message = (message or "").strip()
        if not clean_message:
            raise ValueError("A mensagem nao pode estar vazia.")
        attachment_ids = list(dict.fromkeys(attachment_ids or []))
        if len(attachment_ids) > 10:
            raise ValueError("Envie no maximo 10 anexos por mensagem.")
        stored_attachments = self.attachments.resolve(attachment_ids)

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
                metadata={"attachments": attachment_metadata, "source": "web"},
            )
            job = ChatJob(
                id=uuid.uuid4().hex,
                conversation_id=conversation["id"],
                user_message_id=user_message["id"],
                attachment_ids=attachment_ids,
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
            check_cancelled()
            if not chunk:
                return
            with self._lock:
                job.chunk_count += 1
                sequence = job.chunk_count
            self.event_hub.publish(
                "chat.chunk",
                {"job_id": job.id, "sequence": sequence, "text": chunk},
            )

        try:
            check_cancelled()
            self._ensure_model_ready_callback(on_status)
            memories = self._load_memories(message, on_status)
            prompt = {
                "pergunta": message,
                "documento": "",
                "nome_documento": "",
                "memorias_relevantes": memories,
                "anexos": [(str(item.path), item.name) for item in attachments],
                "modelo_solicitado": model_id or self.settings.llm_model,
                "system_prompt": self._system_prompt(),
                "historico": history,
            }
            prepare_prompt_attachments(prompt, settings=self.settings, fn_status=on_status)
            check_cancelled()
            if prompt.get("caminho_imagem"):
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
            assistant_message = self.conversations.add_message(
                job.conversation_id,
                "assistant",
                response,
                metadata={"source": "web", "job_id": job.id},
            )
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
        with self._lock:
            job.status = "cancelled"
            job.completed_at = _now_iso()
            if self._active_job_id == job.id:
                self._active_job_id = ""
        self.attachments.discard(job.attachment_ids)
        self.event_hub.publish("chat.cancelled", {"job_id": job.id})

    def _load_memories(self, message: str, on_status: Callable[[str], None]) -> list[str]:
        if not self.settings.features.memory:
            return []
        on_status("Consultando memorias relevantes...")
        if self.memory_service is None:
            from core.memory import get_memory_service

            self.memory_service = get_memory_service()
        return self.memory_service.search(message)

    def _system_prompt(self) -> str:
        return (
            f"Voce e {self.settings.assistant.name}, {self.settings.assistant.profile}. "
            "Sua identidade fixa e Celsius. Responda em portugues do Brasil. "
            "O perfil da empresa orienta o contexto, mas nao limita os assuntos."
        )

    def _ensure_model_ready(self, on_status: Callable[[str], None]) -> None:
        from core.llama_cpp import get_llama_manager

        manager = get_llama_manager()
        if manager.is_healthy():
            return
        model_path = self.settings.get_model_path(self.settings.llm_model)
        if not model_path.is_file():
            raise FileNotFoundError(f"Modelo local nao encontrado: {model_path}")
        on_status("Carregando modelo local...")
        started = manager.start(
            model_id=self.settings.llm_model,
            n_gpu_layers=self.settings.model.n_gpu_layers,
            n_ctx=self.settings.model.num_ctx,
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
