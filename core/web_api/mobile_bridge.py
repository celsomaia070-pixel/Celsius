"""Bridge the HTTPS mobile voice client to the shared web chat coordinator."""

from __future__ import annotations

import random
import re
import threading
import time
import unicodedata
from collections.abc import Callable

from core.chat_service import ChatBusyError, ChatCoordinator

WAKE_ACKNOWLEDGEMENTS = (
    "Pode falar",
    "Estou ouvindo",
    "Sim",
    "Opa",
    "Pois nao",
    "To aqui",
)


def _normalize_speech(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


class WakeWordController:
    """Require the wake word before forwarding ambient mobile speech."""

    def __init__(
        self, *, timeout_seconds: float = 12.0, clock: Callable[[], float] = time.monotonic
    ):
        self.timeout_seconds = timeout_seconds
        self._clock = clock
        self._armed_until = 0.0
        self._lock = threading.Lock()

    def process(self, transcript: str) -> dict:
        clean_transcript = (transcript or "").strip()
        normalized = _normalize_speech(clean_transcript)
        wake_match = re.search(r"\bcelsius\b", normalized)

        with self._lock:
            now = self._clock()
            if wake_match:
                command = clean_transcript[wake_match.end() :].strip(" ,.:;!?-")
                if command:
                    self._armed_until = 0.0
                    return {
                        "wake_detected": True,
                        "command_submitted": True,
                        "command": command,
                        "acknowledgement": "",
                    }
                self._armed_until = now + self.timeout_seconds
                return {
                    "wake_detected": True,
                    "command_submitted": False,
                    "command": "",
                    "acknowledgement": random.choice(WAKE_ACKNOWLEDGEMENTS),
                }

            if now <= self._armed_until and clean_transcript:
                self._armed_until = 0.0
                return {
                    "wake_detected": False,
                    "command_submitted": True,
                    "command": clean_transcript,
                    "acknowledgement": "",
                }

        return {
            "wake_detected": False,
            "command_submitted": False,
            "command": "",
            "acknowledgement": "",
        }


class MobileChatBridge:
    """Keep mobile text and voice inside the same Celsius conversation."""

    def __init__(
        self,
        *,
        chat_coordinator: ChatCoordinator,
        whisper_model: str,
        transcriber: Callable | None = None,
        wake_controller: WakeWordController | None = None,
    ):
        self.chat_coordinator = chat_coordinator
        self.whisper_model = whisper_model
        self.transcriber = transcriber or self._transcribe
        self.wake_controller = wake_controller or WakeWordController()
        self._conversation_id = ""
        self._lock = threading.Lock()

    @staticmethod
    def _transcribe(audio: bytes, *, model_name: str) -> str:
        from core.mobile_voice import transcribe_mobile_wav

        return transcribe_mobile_wav(audio, model_name=model_name)

    def handle_command(self, message: str, _source: str = "phone") -> tuple[bool, str]:
        result = self._submit(message)
        return bool(result["ok"]), str(result["message"])

    def handle_voice(self, audio: bytes, _mime_type: str) -> dict:
        try:
            transcript = self.transcriber(audio, model_name=self.whisper_model).strip()
        except Exception as exc:
            return {
                "ok": False,
                "transcript": "",
                "message": f"Erro ao transcrever voz do celular: {exc}",
                "command_submitted": False,
            }

        decision = self.wake_controller.process(transcript)
        payload = {"ok": True, "transcript": transcript, **decision}
        if decision["command_submitted"]:
            payload.update(self._submit(str(decision["command"])))
        elif decision["wake_detected"]:
            payload["message"] = str(decision["acknowledgement"])
        else:
            payload["message"] = "Aguardando a palavra Celsius."
        return payload

    def _submit(self, message: str) -> dict:
        try:
            with self._lock:
                conversation_id = self._conversation_id
            job = self.chat_coordinator.submit(
                message=message,
                conversation_id=conversation_id,
            )
            with self._lock:
                self._conversation_id = str(job["conversation_id"])
            return {
                "ok": True,
                "message": "Comando enviado ao Celsius.",
                "command_submitted": True,
                "job_id": str(job["id"]),
            }
        except ChatBusyError as exc:
            return {"ok": False, "message": str(exc), "command_submitted": False}
        except (LookupError, RuntimeError, ValueError) as exc:
            return {"ok": False, "message": str(exc), "command_submitted": False}
