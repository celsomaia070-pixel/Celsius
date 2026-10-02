"""Opt-in WhatsApp Web connection and durable command inbox for the local agent."""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import queue
import re
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path

from core.agent_modes import get_mode
from core.chat_service import ChatBusyError, ChatNotFoundError
from core.file_security import restrict_private_directory
from core.json_persistence import atomic_write_json, read_json
from core.message_formatting import whatsapp_chunks
from core.users import UserRole
from core.whatsapp_outbox import WhatsAppOutbox


class DeliveryUnavailableError(RuntimeError):
    """Transport rejected the request before any attempt to send."""


def command_text(text: str) -> str:
    """Strip the optional wake name, while keeping task/approval commands intact."""
    return re.sub(r"^\s*(?:celsius\s*[:,]?\s+|/celsius\s+)", "", text, flags=re.I).strip()


def parse_contact_message(text: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"(?:mande|manda|envie|envia|enviar|mandar)\s+(?:uma\s+)?mensagem\s+para\s+"
        r"(?:(?:o|a)\s+)?(?:(?:meu|minha)\s+)?(?:contato\s+)?(.+?)"
        r"(?:\s*:\s*|\s+dizendo(?:\s+que)?\s+|\s+com\s+(?:o\s+)?texto\s+)(.+)",
        text.strip(),
        re.I | re.S,
    )
    return (match[1].strip(), match[2].strip()) if match else None


def route_whatsapp_message(text: str, previous_mode: str = "assistente") -> tuple[str, str]:
    """Keep chat natural; select a capable lane for explicit work requests.

    This only chooses existing modes. Tool permissions and confirmation checks
    remain enforced by the shared coordinator and task runner.
    """
    clean = command_text(text)
    if re.match(r"^(?:AUTORIZAR\s|CANCELAR\s|RETOMAR\s|TAREFAS\s*$)", clean, re.I):
        return clean, get_mode(previous_mode).id
    from core.agent_modes import detect_mode
    from core.message_intent import classify_intent, normalize_text, strip_task_prefix

    intent = classify_intent(clean)
    if intent.quick_key:
        return strip_task_prefix(clean), "assistente"
    if intent.operational:
        words = normalize_text(clean)
        mode = detect_mode(words) or ("executor" if intent.kind == "task" else previous_mode)
        if re.search(r"\b(?:pesquis\w*|noticias?|previsao|meteorolog\w*|cotacao|clima)\b", words):
            mode = "pesquisador"
        elif re.search(r"\b(?:pei|paee|pdi)\b", words):
            mode = "documentos"
        if intent.kind == "task" and not intent.explicit_task:
            clean = "TAREFA: " + clean
        return clean, get_mode(mode).id
    return clean, get_mode(previous_mode).id


class WhatsAppService:
    """One explicitly paired account, self-chat only, sharing the desktop coordinator."""

    def __init__(self, *, settings, coordinator, user_service, event_hub):
        self.settings = settings
        self.coordinator = coordinator
        self.users = user_service
        self.event_hub = event_hub
        self.root = Path(settings.data_dir) / "whatsapp"
        self.root.mkdir(parents=True, exist_ok=True)
        self.config_file = self.root / "connection.json"
        self.config = read_json(self.config_file, {}) or {}
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._welcome_lock = threading.Lock()
        self._welcome_pending = False
        self._welcome_error = ""
        self._process = None
        self._stop = threading.Event()
        self._worker = None
        self._requests = {}
        self._events: queue.Queue[str] = queue.Queue(maxsize=64)
        self._state = "disconnected"
        self._qr = ""
        self._self_ids = set()
        self._error = ""
        self._conversation_id = self.config.get("conversation_id", "")
        self._agent_mode = get_mode(self.config.get("agent_mode")).id
        self._active = None
        self.db = sqlite3.connect(self.root / "inbox.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS inbox (
            id TEXT PRIMARY KEY, jid TEXT NOT NULL, text TEXT NOT NULL,
            state TEXT NOT NULL, created REAL NOT NULL, job_id TEXT DEFAULT '')""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS confirmations (
            code TEXT PRIMARY KEY, jid TEXT NOT NULL, recipient TEXT NOT NULL,
            body TEXT NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL)""")
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(inbox)")}
        if "queued_ack" not in columns:
            self.db.execute("ALTER TABLE inbox ADD COLUMN queued_ack INTEGER NOT NULL DEFAULT 0")
        # A crashed in-flight stock operation cannot safely be replayed automatically.
        self.db.execute(
            "UPDATE inbox SET state='interrupted' WHERE state IN ('running','dispatching')"
        )
        self.db.commit()
        self.outbox = WhatsAppOutbox(self.root / "outbox.db", data_root=settings.data_dir)

    def status(self, *, include_qr=False):
        with self._lock:
            result = {
                "state": self._state,
                "connected": self._state == "connected",
                "owner_id": self.config.get("owner_id", ""),
                "error": self._error,
                "pending": self.db.execute(
                    "SELECT COUNT(*) FROM inbox WHERE state='queued'"
                ).fetchone()[0],
                "active_job_id": self._active["job_id"] if self._active else "",
                "conversation_id": self._conversation_id,
                "self_chat_url": self._self_chat_url() if self._state == "connected" else "",
                "welcome_sent": self._state == "connected"
                and self.config.get("welcome_jid") == self._phone_jid(),
                "welcome_error": self._welcome_error,
                "delivery": self.outbox.counts(self._self_ids),
            }
            if include_qr and self._qr:
                import qrcode

                image = qrcode.make(self._qr)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                result["qr_image"] = (
                    "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
                )
            return result

    def _save_config(self):
        atomic_write_json(self.config_file, self.config)

    def _phone_jid(self):
        return next(
            (
                jid
                for jid in sorted(self._self_ids)
                if re.fullmatch(r"\d{10,15}@s\.whatsapp\.net", jid)
            ),
            "",
        )

    def _self_chat_url(self):
        jid = self._phone_jid()
        return "https://wa.me/" + jid.split("@")[0] if jid else ""

    def open_self_chat(self, *, resend=False):
        """Create the owner's self-chat; called outside the transport reader thread."""
        with self._welcome_lock:
            with self._lock:
                owner = self.users.get_user(self.config.get("owner_id", ""))
                jid = self._phone_jid()
                if self._state != "connected" or not jid:
                    raise RuntimeError(
                        "Aguarde o WhatsApp terminar de conectar para abrir a conversa."
                    )
                if not owner or not owner.is_active or owner.role == UserRole.VIEWER:
                    raise ValueError("Entre com a conta que conectou o WhatsApp.")
                self._welcome_pending = False
                if not resend and self.config.get("welcome_jid") == jid:
                    return self.status()
            try:
                self._reply(
                    jid,
                    "Conectado ao seu computador!\n\nEsta é sua conversa com o Celsius. "
                    "Envie AJUDA para ver exemplos ou escreva seu pedido aqui. "
                    "Os resultados e documentos serão enviados nesta conversa.\n\n"
                    "Mantenha o computador ligado e o Celsius aberto.",
                )
            except (RuntimeError, OSError):
                with self._lock:
                    self._welcome_error = "A mensagem inicial não foi confirmada. Abra sua conversa pelo botão abaixo ou tente Enviar mensagem inicial."
                raise
            with self._lock:
                if self._state == "connected" and jid in self._self_ids:
                    self.config["welcome_jid"] = jid
                    self._welcome_error = ""
                    self._save_config()
                return self.status()

    def start(self, owner_id: str):
        with self._lock:
            if self.config.get("owner_id") not in (None, "", owner_id):
                raise ValueError("Esta conexão pertence a outra conta do Celsius.")
            owner = self.users.get_user(owner_id)
            if owner is None or not owner.is_active or owner.role == UserRole.VIEWER:
                raise ValueError("Entre com uma conta que possa enviar comandos.")
            if self._process and self._process.poll() is None:
                return self.status(include_qr=True)
            node = shutil.which("node")
            folder = Path(__file__).resolve().parents[1] / "integrations" / "whatsapp"
            if not node or not (folder / "node_modules" / "@whiskeysockets" / "baileys").exists():
                raise RuntimeError(
                    "Instale a conexão WhatsApp usando scripts/install-whatsapp.ps1."
                )
            restrict_private_directory(self.root)
            restrict_private_directory(self.root / "session")
            self._stop.clear()
            session = self.root / "session"
            if self.config.pop("session_stale", False) and session.exists():
                session.rename(self.root / ("revoked-session-" + uuid.uuid4().hex))
            self._error = ""
            self._qr = ""
            self._state = "connecting"
            self.config.update(owner_id=owner_id, enabled=True)
            self._save_config()
            kwargs = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else {}
            )
            self._process = subprocess.Popen(  # type: ignore[call-overload]
                [node, str(folder / "bridge.mjs"), str(self.root / "session")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=folder,
                **kwargs,
            )
            threading.Thread(
                target=self._read,
                args=(self._process,),
                daemon=True,
                name="CelsiusWhatsAppConnection",
            ).start()
            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._work, daemon=True, name="CelsiusWhatsAppCommands"
                )
                self._worker.start()
            return self.status()

    def resume(self):
        if self.config.get("enabled") and self.config.get("owner_id"):
            try:
                self.start(self.config["owner_id"])
            except (RuntimeError, ValueError, OSError):
                self._state = "error"
                self._error = "Não foi possível restaurar a conexão WhatsApp. Abra a conexão e tente novamente."

    def pause(self):
        with self._lock:
            self.config["enabled"] = False
            self._save_config()
        self.shutdown()

    def logout(self):
        if self._process and self._process.poll() is None:
            self._rpc("logout")
        self.pause()

    def shutdown(self):
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            try:
                process.stdin.close()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=3)
        with self._lock:
            self._qr = ""
            self._state = "disconnected"

    def _rpc(self, action: str, **payload):
        request_id = uuid.uuid4().hex
        result: queue.Queue[dict] = queue.Queue(maxsize=1)
        with self._lock:
            process = self._process
            if not process or process.poll() is not None:
                raise DeliveryUnavailableError("WhatsApp desconectado.")
            self._requests[request_id] = result
        try:
            with self._write_lock:
                process.stdin.write(
                    json.dumps({"id": request_id, "action": action, **payload}, ensure_ascii=False)
                    + "\n"
                )
                process.stdin.flush()
            try:
                response = result.get(timeout=30)
            except queue.Empty as exc:
                raise RuntimeError(
                    "O WhatsApp não confirmou a entrega. Verifique a conexão antes de reenviar."
                ) from exc
            if not response.get("ok"):
                raise RuntimeError(response.get("error", "O WhatsApp não confirmou a operação."))
            return response.get("result", {})
        finally:
            with self._lock:
                self._requests.pop(request_id, None)

    def _read(self, process):
        for line in process.stdout:
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            self.receive(event)
        with self._lock:
            if process is self._process and not self._stop.is_set():
                self._state = "error"
                self._qr = ""
                self._error = "Conexão encerrada. Clique em Conectar para tentar novamente."

    def receive(self, event: dict):
        kind = event.get("type")
        with self._lock:
            if kind == "result":
                waiter = self._requests.get(event.get("request_id"))
                if waiter:
                    waiter.put_nowait(event)
                return
            if kind in {"qr", "connected", "reconnecting", "logged_out", "error"}:
                self._state = {"qr": "pairing", "logged_out": "disconnected"}.get(kind, kind)
                self._qr = event.get("qr", "")
                if kind == "connected":
                    self._self_ids = set(event.get("self_ids", []))
                    self._error = ""
                    self._welcome_error = ""
                    self._welcome_pending = (
                        bool(self._phone_jid())
                        and self.config.get("welcome_jid") != self._phone_jid()
                    )
                if kind == "error":
                    self._error = "Não foi possível conectar ao WhatsApp. Tente novamente."
                if kind == "logged_out":
                    self.config["enabled"] = False
                    self.config["session_stale"] = True
                    self._save_config()
                self.event_hub.publish("whatsapp.connection", {"state": self._state})
                # Diagnostic state excludes QR, account identifiers and messages.
                atomic_write_json(
                    self.root / "status.json",
                    {
                        "state": self._state,
                        "updated": time.time(),
                        "disconnect_code": event.get("code"),
                        "self_chat_available": bool(self._phone_jid())
                        if kind == "connected"
                        else False,
                    },
                )
                return
            if kind != "message" or self._state != "connected":
                return
            owner = self.users.get_user(self.config.get("owner_id", ""))
            if not owner or not owner.is_active or owner.role == UserRole.VIEWER:
                return
            # Enforce again in Python: JS transport is not an authorization boundary.
            if event.get("from_me") is not True or event.get("jid") not in self._self_ids:
                return
            message_id, jid, text = event.get("id"), event.get("jid"), event.get("text")
            if not isinstance(message_id, str) or not message_id or not isinstance(text, str):
                return
            if text.startswith("Celsius\n") or not text.strip() or len(text) > 20000:
                return
            if (
                self.db.execute("SELECT COUNT(*) FROM inbox WHERE state='queued'").fetchone()[0]
                >= 32
            ):
                return
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO inbox(id,jid,text,state,created) VALUES(?,?,?,'queued',?)",
                (message_id, jid, text, time.time()),
            )
            self.db.commit()
            if cursor.rowcount:
                with suppress(queue.Full):
                    self._events.put_nowait(message_id)

    def _reply(self, jid, text):
        for chunk in whatsapp_chunks(text):
            self._rpc("send", jid=jid, text="Celsius\n" + chunk)

    def _deliver_results(self):
        for item in self.outbox.pending(self._self_ids):
            if self._state != "connected":
                return
            payload = json.loads(item["payload"])
            self.outbox.mark(item["id"], "sending")
            try:
                if item["kind"] == "document":
                    output = self.coordinator.outputs.get(payload["attachment_id"])
                    if not output.path.is_file():
                        raise FileNotFoundError("O arquivo gerado não está disponível.")
                    payload = {
                        "path": str(output.path),
                        "name": output.name,
                        "mime": mimetypes.guess_type(output.name)[0] or "application/octet-stream",
                        "text": "Celsius\nArquivo gerado no computador.",
                    }
                self._rpc("send", jid=item["jid"], **payload)
            except DeliveryUnavailableError:
                self.outbox.mark(item["id"], "queued")
                self._error = (
                    "Resultado salvo. A entrega será retomada quando o WhatsApp reconectar."
                )
                return
            except (FileNotFoundError, ChatNotFoundError, ValueError):
                self.outbox.mark(item["id"], "failed", "Arquivo indisponível para entrega.")
                self._error = "Um arquivo não pôde ser enviado. Confira os anexos no computador."
            except (RuntimeError, OSError):
                self.outbox.mark(item["id"], "uncertain", "Entrega sem confirmação do WhatsApp.")
                self._error = (
                    "Resultado salvo, mas a entrega não foi confirmada. "
                    "Confira a conversa e use REENVIAR RESULTADO se necessário."
                )
                return
            else:
                self.outbox.mark(item["id"], "sent")

    def _set_state(self, message_id, state, job_id=""):
        with self._lock:
            self.db.execute(
                "UPDATE inbox SET state=?, job_id=? WHERE id=?", (state, job_id, message_id)
            )
            self.db.commit()

    def _control(self, row):
        message_id, jid, raw = row
        if jid not in self._self_ids:
            self._set_state(message_id, "interrupted")
            return True
        text = command_text(raw)
        from core.message_intent import normalize_text

        normalized = normalize_text(text)
        if normalized in {"ajuda", "help"}:
            self._reply(
                jid,
                "Escreva aqui seus pedidos. Exemplos: gere um relatório de estoque; dê entrada de 10 peças; mande mensagem para João: texto.\nUse STATUS, CANCELAR, NOVA CONVERSA ou REENVIAR RESULTADO. Envios a contatos pedem confirmação antes de enviar.",
            )
        elif normalized == "status":
            with self._lock:
                pending = self.db.execute(
                    "SELECT COUNT(*) FROM inbox WHERE state='queued' AND id<>?", (message_id,)
                ).fetchone()[0]
            if self._active:
                job = self.coordinator.get_job(self._active["job_id"])
                status = (
                    job.get("status_message") or "Estou trabalhando no seu pedido no computador."
                )
            elif pending:
                status = f"Há {pending} pedido(s) na fila, aguardando o computador terminar a tarefa atual."
            else:
                status = "Aguardando seus pedidos. O computador precisa continuar ligado e com o Celsius aberto."
            self._reply(jid, status)
        elif normalized == "reenviar resultado":
            retry = self.outbox.retry_latest(jid)
            self._reply(
                jid,
                "Vou reenviar somente a entrega pendente; a tarefa não será executada novamente."
                if retry
                else "Não há entrega sem confirmação para reenviar.",
            )
        elif normalized == "cancelar":
            if self._active:
                self.coordinator.cancel(self._active["job_id"])
            self._reply(
                jid,
                "Cancelamento solicitado."
                if self._active
                else "Não há tarefa WhatsApp em execução.",
            )
        elif normalized == "nova conversa":
            if self._active:
                self._reply(
                    jid, "Aguarde a tarefa atual ou use CANCELAR antes de iniciar outra conversa."
                )
            else:
                self._conversation_id = ""
                self.config["conversation_id"] = ""
                self._agent_mode = "assistente"
                self.config["agent_mode"] = self._agent_mode
                self._save_config()
                self._reply(
                    jid, "Pronto. Seu próximo pedido iniciará uma nova conversa no computador."
                )
        elif re.fullmatch(r"confirmar\s+[a-f0-9]{8}", text, re.I):
            code = text.split()[-1].lower()
            with self._lock:
                pending = self.db.execute(
                    "SELECT recipient,body FROM confirmations WHERE code=? AND jid=? AND state='pending' AND expires>?",
                    (code, jid, time.time()),
                ).fetchone()
                if pending:
                    self.db.execute(
                        "UPDATE confirmations SET state='sending' WHERE code=?", (code,)
                    )
                    self.db.commit()
            if not pending:
                self._reply(jid, "Confirmação inválida, já usada ou expirada.")
            else:
                try:
                    self._rpc("send", jid=pending[0], text=pending[1])
                except RuntimeError:
                    self._reply(
                        jid,
                        "Não recebi confirmação de entrega. Verifique a conversa do contato antes de tentar outro envio.",
                    )
                else:
                    self._reply(jid, "Mensagem enviada e confirmada pelo WhatsApp.")
        else:
            contact_message = parse_contact_message(text)
            if not contact_message:
                if re.match(
                    r"^(?:mande|manda|envie|envia|enviar|mandar)\s+(?:uma\s+)?mensagem\s+para\b",
                    text,
                    re.I,
                ):
                    self._reply(
                        jid,
                        "Informe o destinatário e o texto. Exemplo: mande mensagem para João: o relatório está pronto.",
                    )
                    self._set_state(message_id, "completed")
                    return True
                return False
            contact, body = contact_message
            matches = self._rpc("resolve", contact=contact).get("matches", [])
            if len(matches) != 1:
                self._reply(
                    jid,
                    "Não encontrei um contato único. Informe o telefone com DDI e DDD, por exemplo: mande mensagem para +5514999999999: texto.",
                )
            else:
                code = secrets.token_hex(4)
                with self._lock:
                    self.db.execute(
                        "INSERT INTO confirmations VALUES(?,?,?,?,?,'pending')",
                        (code, jid, matches[0]["jid"], body, time.time() + 600),
                    )
                    self.db.commit()
                self._reply(
                    jid,
                    f"Enviar para {matches[0]['name']}?\n\n{body}\n\nResponda CONFIRMAR {code} em até 10 minutos.",
                )
        self._set_state(message_id, "completed")
        return True

    def _work(self):
        while not self._stop.is_set():
            try:
                try:
                    message_id = self._events.get(timeout=0.5)
                except queue.Empty:
                    message_id = None
                if self._state != "connected":
                    continue
                owner = self.users.get_user(self.config.get("owner_id", ""))
                if not owner or not owner.is_active or owner.role == UserRole.VIEWER:
                    continue
                if self._welcome_pending:
                    # Preserve commands; delivery uncertainty is shown in the UI.
                    with suppress(RuntimeError, OSError):
                        self.open_self_chat()
                if message_id:
                    with self._lock:
                        row = self.db.execute(
                            "SELECT id,jid,text FROM inbox WHERE id=? AND state='queued'",
                            (message_id,),
                        ).fetchone()
                    if row:
                        self._control(row)
                self._tick()
            except (RuntimeError, OSError, ChatNotFoundError, ValueError):
                self._error = (
                    "Uma operação não foi concluída. Confira a conexão e a tarefa no computador."
                )
                self._stop.wait(1)

    def _tick(self):
        owner = self.users.get_user(self.config.get("owner_id", ""))
        if not owner or not owner.is_active or owner.role == UserRole.VIEWER:
            return
        self._deliver_results()
        if self._active:
            job = self.coordinator.get_job(self._active["job_id"])
            if job["status"] not in {"completed", "failed", "cancelled"}:
                return
            active = self._active
            # Persist delivery before releasing execution. A transport failure
            # must never re-run the task or lose its already produced files.
            if active["jid"] in self._self_ids:
                self.outbox.enqueue(active["id"], active["jid"], job)
            self._set_state(active["id"], job["status"], job["id"])
            self._active = None
            if active["jid"] not in self._self_ids:
                return
            self._deliver_results()
        with self._lock:
            row = self.db.execute(
                "SELECT id,jid,text FROM inbox WHERE state='queued' ORDER BY created LIMIT 1"
            ).fetchone()
        if not row:
            return
        message_id, jid, raw = row
        if self._control(row):
            return
        text, mode = route_whatsapp_message(raw, self._agent_mode)
        self._set_state(message_id, "dispatching")
        try:
            job = self.coordinator.submit(
                message=text,
                conversation_id=self._conversation_id,
                agent_mode=mode,
                source="whatsapp",
            )
        except ChatBusyError:
            self._set_state(message_id, "queued")
            with self._lock:
                acknowledged = self.db.execute(
                    "UPDATE inbox SET queued_ack=1 WHERE id=? AND queued_ack=0", (message_id,)
                ).rowcount
                self.db.commit()
            if acknowledged:
                self._reply(
                    jid,
                    "O Celsius está ocupado no computador. Seu pedido entrou na fila e será executado quando a tarefa atual terminar.",
                )
            return  # shared single inference slot: preserve FIFO until desktop is free
        except ChatNotFoundError:
            self._set_state(message_id, "queued")
            self._conversation_id = ""
            return
        self._active = {"id": message_id, "jid": jid, "job_id": job["id"]}
        self._conversation_id = job["conversation_id"]
        self.config["conversation_id"] = self._conversation_id
        if get_mode(mode).can_plan:
            self._agent_mode = mode
            self.config["agent_mode"] = mode
        self._save_config()
        self._set_state(message_id, "running", job["id"])
        self._reply(
            jid,
            "Pedido recebido. Estou trabalhando no computador; enviarei o resultado por aqui."
            if re.match(r"^TAREFA\s*:", text, re.I)
            else "Mensagem recebida. Estou preparando a resposta no computador.",
        )
