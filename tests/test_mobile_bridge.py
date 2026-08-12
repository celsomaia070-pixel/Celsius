"""Tests for wake-word routing between the mobile client and web chat."""

from core.web_api.mobile_bridge import MobileChatBridge, WakeWordController


class FakeChatCoordinator:
    def __init__(self):
        self.messages = []

    def submit(self, *, message, conversation_id="", **_kwargs):
        self.messages.append((message, conversation_id))
        return {
            "id": f"job-{len(self.messages)}",
            "conversation_id": conversation_id or "abc123def456",
        }


def test_wake_word_arms_next_utterance(monkeypatch):
    monkeypatch.setattr("core.web_api.mobile_bridge.random.choice", lambda _items: "Estou ouvindo")
    controller = WakeWordController()

    wake = controller.process("Celsius")
    command = controller.process("mostre meu estoque")

    assert wake == {
        "wake_detected": True,
        "command_submitted": False,
        "command": "",
        "acknowledgement": "Estou ouvindo",
    }
    assert command["command_submitted"] is True
    assert command["command"] == "mostre meu estoque"


def test_wake_word_and_command_can_share_one_utterance():
    decision = WakeWordController().process("Celsius, gere um relatorio do estoque")

    assert decision["wake_detected"] is True
    assert decision["command_submitted"] is True
    assert decision["command"] == "gere um relatorio do estoque"


def test_ambient_speech_is_not_sent_to_chat():
    coordinator = FakeChatCoordinator()
    bridge = MobileChatBridge(
        chat_coordinator=coordinator,
        whisper_model="small",
        transcriber=lambda _audio, **_kwargs: "conversa ao fundo",
    )

    result = bridge.handle_voice(b"wav", "audio/wav")

    assert result["ok"] is True
    assert result["command_submitted"] is False
    assert coordinator.messages == []


def test_mobile_command_keeps_same_conversation():
    coordinator = FakeChatCoordinator()
    transcripts = iter(("Celsius", "quantos itens tenho no estoque"))
    bridge = MobileChatBridge(
        chat_coordinator=coordinator,
        whisper_model="small",
        transcriber=lambda _audio, **_kwargs: next(transcripts),
    )

    wake = bridge.handle_voice(b"wav", "audio/wav")
    command = bridge.handle_voice(b"wav", "audio/wav")
    bridge.handle_command("e quais estao criticos", "phone_text")

    assert wake["command_submitted"] is False
    assert command["command_submitted"] is True
    assert coordinator.messages == [
        ("quantos itens tenho no estoque", ""),
        ("e quais estao criticos", "abc123def456"),
    ]
