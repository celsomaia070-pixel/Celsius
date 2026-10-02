"""Mode routing: lexical keywords, semantic classification and precedence.

The bug these cover: ``detect_mode`` was documented but driven by an empty
keyword set, so a message could never select a mode on its own, and a long
task re-decided its lane on every turn.

The encoder is faked with one orthogonal direction per mode, so a test declares
the winner by naming a direction and every other mode scores exactly 0.0.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core import agent_modes
from core.agent_modes import (
    DEFAULT_MODE_ID,
    MODES,
    classify_mode,
    detect_mode,
    parse_mode_command,
    reset_mode_embeddings,
    resolve_mode,
)

_DIM = 8
_MODES = [mode.id for mode in MODES]


def _direction(mode_id: str) -> np.ndarray:
    vector = np.zeros(_DIM)
    vector[_MODES.index(mode_id)] = 1.0
    return vector


class FakeEncoder:
    """Encodes mode profiles to one direction each, and one known query.

    Any text that is neither a mode profile nor the registered query resolves to
    an orthogonal direction, which is what a real encoder does for an unrelated
    sentence: cosine 0.0 against every mode.
    """

    def __init__(self, query_text: str, query_vector):
        self._query_text = query_text
        self._query_vector = query_vector
        self.batches: list[list[str]] = []

    def encode(self, texts):
        texts = list(texts)
        self.batches.append(texts)
        vectors = []
        for text in texts:
            if text == self._query_text:
                vectors.append(self._query_vector)
            elif text in _MODE_PROFILE_TO_ID:
                vectors.append(_direction(_MODE_PROFILE_TO_ID[text]))
            else:
                vectors.append(_UNRELATED)
        return np.array(vectors)


#: Orthogonal to every mode direction, so it contributes no similarity at all.
_UNRELATED = np.zeros(_DIM)

#: A real orthogonal axis, used to build partially-aligned queries.
_OFF_AXIS = np.zeros(_DIM)
_OFF_AXIS[_DIM - 1] = 1.0

#: Populated from the real profiles so the fake stays in sync with the module
#: without re-encoding the mode text by hand.
_MODE_PROFILE_TO_ID = {agent_modes.mode_profile_text(mode): mode.id for mode in MODES}


@pytest.fixture
def fake_encoder(monkeypatch):
    """Install a fake encoder, clearing the mode cache around the test."""

    def install(text: str, mode_id: str | None = None, *, weight: float = 1.0):
        """Point *text* at *mode_id*'s direction.

        ``weight`` below 1.0 mixes in an orthogonal component, producing a real
        partial score so a threshold can be tested.
        """
        if mode_id is None:
            query_vector = _UNRELATED
        else:
            # cos(weight) == weight, so the resulting score is exactly *weight*.
            angle = math.acos(weight)
            query_vector = weight * _direction(mode_id) + math.sin(angle) * _OFF_AXIS
        encoder = FakeEncoder(text, query_vector)
        reset_mode_embeddings()
        monkeypatch.setattr("core.embeddings.try_get_sentence_transformer", lambda _n: encoder)
        return encoder

    yield install
    reset_mode_embeddings()


@pytest.fixture
def agent_settings():
    """The **live** ``AgentModeSettings``, not the session-scoped snapshot.

    ``core.settings.reset_settings()`` rebuilds the singleton, so the session
    ``settings`` fixture can hold a stale object whose mutations production code
    never sees. Resolving it per test keeps these assertions honest.
    """
    from core.settings import get_settings

    return get_settings().agent


def test_every_mode_declares_keywords():
    # A mode with no keyword is unreachable without a command: the pre-existing
    # state of the module.
    for mode in MODES:
        assert mode.keywords, f"mode {mode.id} has no keywords"


class TestDetectMode:
    def test_finds_a_mode_from_its_keyword(self):
        assert detect_mode("quero ver o estoque") == "estoque"

    def test_matches_on_word_boundaries(self):
        assert detect_mode("explique o itensismo da palavra") is None

    def test_returns_none_when_nothing_matches(self):
        assert detect_mode("Explique energia solar") is None

    def test_empty_text_is_not_a_mode(self):
        assert detect_mode("") is None
        assert detect_mode("   ") is None

    def test_is_case_and_accent_insensitive(self):
        assert detect_mode("QUERO VER O ESTOQUE") == "estoque"
        assert detect_mode("quero um SCRIPT em Python") == "desenvolvedor"


class TestClassifyMode:
    def test_threshold_blocks_a_weak_match(self, fake_encoder):
        # A partially-aligned query scores below the default 0.5 bar.
        fake_encoder("meu estoque", "estoque", weight=0.4)

        modo, score = classify_mode("meu estoque")

        assert score == pytest.approx(0.4, abs=1e-6)
        assert modo is None

    def test_strong_match_wins(self, fake_encoder):
        fake_encoder("meu estoque", "estoque")

        modo, score = classify_mode("meu estoque")

        assert modo == "estoque"
        assert score == pytest.approx(1.0)

    def test_orthogonal_query_clears_no_mode(self, fake_encoder):
        fake_encoder("meu estoque", "estoque")

        modo, score = classify_mode("texto sem relacao com nenhum modo")

        assert modo is None
        assert score == pytest.approx(0.0)

    def test_disabled_router_reports_nothing(self, fake_encoder, agent_settings, monkeypatch):
        fake_encoder("meu estoque", "estoque")
        monkeypatch.setattr(agent_settings, "auto_route_enabled", False)

        assert classify_mode("meu estoque") == (None, 0.0)

    def test_missing_encoder_reports_nothing(self, monkeypatch):
        monkeypatch.setattr("core.embeddings.try_get_sentence_transformer", lambda _name: None)
        reset_mode_embeddings()

        assert classify_mode("meu estoque") == (None, 0.0)

    def test_empty_text_is_not_classified(self):
        assert classify_mode("") == (None, 0.0)


class TestResolveMode:
    def test_explicit_command_beats_everything(self, fake_encoder):
        fake_encoder("meu estoque", "estoque")

        resolvido = resolve_mode("modo pesquisador", pinned="documentos", requested="executor")

        assert resolvido == "pesquisador"

    def test_pinned_mode_beats_classification(self, fake_encoder):
        # The flapping case: a task that decided "documentos" must stay there
        # even when a later slice reads like another lane.
        fake_encoder("meu estoque", "estoque")

        assert resolve_mode("meu estoque", pinned="documentos") == "documentos"

    def test_explicit_non_default_request_beats_classification(self, fake_encoder):
        fake_encoder("meu estoque", "estoque")

        assert resolve_mode("meu estoque", requested="executor") == "executor"

    def test_default_request_does_not_pin(self, fake_encoder):
        # ``requested == default`` is what the UI sends when the user never
        # chose a lane, so it must not stop the router.
        fake_encoder("meu estoque", "estoque")

        assert resolve_mode("meu estoque", requested=DEFAULT_MODE_ID) == "estoque"

    def test_classification_wins_over_lexical(self, fake_encoder):
        fake_encoder("quero ver o estoque", "documentos")

        assert resolve_mode("quero ver o estoque") == "documentos"

    def test_lexical_is_the_fallback_when_classification_fails(self, fake_encoder):
        fake_encoder("texto sem relacao", "estoque")

        assert resolve_mode("quero ver o estoque") == "estoque"

    def test_falls_back_to_the_requested_mode(self, fake_encoder):
        # The encoder is pointed at a different sentence, so this one scores 0.0
        # and no keyword matches: the default has to win.
        fake_encoder("texto sem relacao", "estoque")

        assert resolve_mode("Explique energia solar") == DEFAULT_MODE_ID

    def test_never_returns_an_invalid_mode(self, fake_encoder):
        fake_encoder("meu estoque", "estoque")

        assert resolve_mode("meu estoque", pinned="modo-inexistente") in _MODES

    def test_honours_an_explicit_default(self, fake_encoder):
        fake_encoder("texto sem relacao", "estoque")

        assert resolve_mode("Explique energia solar", default="pesquisador") == "pesquisador"


class TestParseModeCommand:
    def test_accepts_a_switch_phrase(self):
        assert parse_mode_command("modo estoque") == "estoque"

    def test_ignores_an_ordinary_question(self):
        assert parse_mode_command("quero ver o estoque") is None

    def test_ignores_an_unknown_mode(self):
        assert parse_mode_command("modoinexistente qualquer") is None
