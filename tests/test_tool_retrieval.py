"""Hybrid tool retrieval: semantic union, intent gate and top-k floor.

The encoder is faked with explicit, orthogonal one-hot directions so a test can
say exactly which tool is "close" to the query and prove which signal produced
the result. ``tests/conftest.py`` mocks SentenceTransformer with a *random*
encoder; the scores that produces are ~0 (sd ~= 0.05 for 384 dims), far below
``tool_retrieval_min_score`` and ``operational_intent_min_score``, so production
code paths stay deterministic under the suite's own mock too.
"""

from __future__ import annotations

import numpy as np
import pytest

from ai import react as ai_react
from ai import tool_retrieval
from ai.tools import REGISTRO_FERRAMENTAS
from core.agent_modes import READ_CORE

_DIM = 8


def _direction(index: int) -> np.ndarray:
    vector = np.zeros(_DIM)
    vector[index] = 1.0
    return vector


#: Orthogonal directions, so cosine similarity is 1.0 only for the pair that
#: shares a direction and exactly 0.0 for everything else.
DOCUMENTS = _direction(0)
STOCK = _direction(1)
CODE = _direction(2)
SCHOOL = _direction(3)
UNRELATED = _direction(7)


def _tool_direction(text: str) -> np.ndarray:
    """Map a tool's semantic text to the direction that tool stands for."""
    if "listar documentos rag" in text:
        return DOCUMENTS
    if "listar estoque" in text:
        return STOCK
    if "gerar relatorio local" in text:
        return SCHOOL
    return CODE


class FakeEncoder:
    """Deterministic stand-in for SentenceTransformer.

    Tool texts resolve through :func:`_tool_direction`; the query resolves
    through ``query_direction``, so a test declares its scenario by naming one
    direction instead of writing a resolver. Every batch is recorded, letting a
    test assert the static tool embeddings were encoded exactly once.
    """

    def __init__(self, query_direction):
        self._query_direction = query_direction
        self.batches: list[list[str]] = []

    def encode(self, texts):
        texts = list(texts)
        self.batches.append(texts)
        return np.array(
            [
                self._query_direction if text == self._query_text else _tool_direction(text)
                for text in texts
            ]
        )

    def for_query(self, text: str) -> FakeEncoder:
        self._query_text = text
        return self


@pytest.fixture
def fake_encoder(monkeypatch):
    """Install a fake encoder and clear the cached vectors around the test."""

    def install(text: str, direction) -> FakeEncoder:
        encoder = FakeEncoder(direction).for_query(text)
        tool_retrieval.reset_tool_embeddings()
        monkeypatch.setattr(tool_retrieval, "get_embedding_model", lambda: encoder)
        return encoder

    yield install
    tool_retrieval.reset_tool_embeddings()


@pytest.fixture
def agent_settings(monkeypatch):
    """The **live** ``AgentModeSettings``, not the session-scoped snapshot.

    ``core.settings.reset_settings()`` (exercised by ``tests/test_settings.py``)
    rebuilds the singleton, which leaves the session ``settings`` fixture holding
    a stale object whose mutations production code never sees. Resolving it per
    test keeps these assertions honest, and ``monkeypatch`` still undoes every
    change, so nothing leaks forward either.
    """
    from core.settings import get_settings

    return get_settings().agent


def _names(question: str, *, has_document: bool = False) -> set[str]:
    return {tool.nome for tool in ai_react._filtrar_ferramentas(question, has_document=has_document)}


def _lexical_names(question: str) -> set[str]:
    """What the keyword map alone decides, with retrieval disabled."""
    return set(ai_react._keywords_para_ferramentas(question))


def _fold(value: str) -> str:
    return tool_retrieval._normalize(value)


class TestSemanticText:
    def test_built_from_the_registered_tool(self):
        ferramenta = next(t for t in REGISTRO_FERRAMENTAS if t.nome == "listar_documentos_rag")

        texto = tool_retrieval.tool_semantic_text(ferramenta)

        assert "listar documentos rag" in texto
        assert _fold(ferramenta.descricao) in texto

    def test_includes_parameter_vocabulary(self):
        ferramenta = next(t for t in REGISTRO_FERRAMENTAS if t.nome == "buscar_item_estoque")

        texto = tool_retrieval.tool_semantic_text(ferramenta)

        parametros = list(ferramenta.schema.get("properties", {}))
        assert parametros
        assert any(nome.replace("_", " ") in texto for nome in parametros)

    def test_never_returns_empty(self):
        for ferramenta in REGISTRO_FERRAMENTAS:
            assert tool_retrieval.tool_semantic_text(ferramenta).strip()


class TestIntentGate:
    def test_general_question_is_not_operational(self):
        assert not tool_retrieval.is_operational("Explique energia solar")

    def test_local_data_noun_opens_the_gate(self):
        assert tool_retrieval.is_operational("quais documentos eu tenho")
        assert tool_retrieval.is_operational("qual o estoque de parafusos")
        assert tool_retrieval.is_operational("meus clientes")

    def test_empty_question_is_not_operational(self):
        assert not tool_retrieval.is_operational("")
        assert not tool_retrieval.is_operational("   ")

    def test_noun_must_match_on_word_boundaries(self):
        # "itensismo" contains "itens" but is not a stock request.
        assert not tool_retrieval.is_operational("explique o itensismo da palavra")

    def test_high_similarity_alone_opens_the_gate(self):
        # The paraphrase carries no known noun; confidence is the only reason left.
        assert tool_retrieval.is_operational("me mostre o que guardei", {"listar_estoque": 0.9})

    def test_low_similarity_does_not_open_the_gate(self):
        assert not tool_retrieval.is_operational("me mostre o que guardei", {"listar_estoque": 0.1})


class TestSelection:
    def test_lexical_map_alone_misses_the_paraphrase(self):
        # Establishes the bug this module exists to fix: the phrase names no tool
        # keyword, so the document tools are never offered.
        assert "listar_documentos_rag" not in _lexical_names("quais documentos eu tenho")

    def test_semantic_retrieval_finds_the_hidden_tool(self, fake_encoder):
        fake_encoder("quais documentos eu tenho", DOCUMENTS)

        assert "listar_documentos_rag" in _names("quais documentos eu tenho")

    def test_general_question_keeps_zero_tools(self, fake_encoder):
        # No lexical hit, no domain noun, and the encoder says the question is
        # unrelated to every tool: the model must still be reached with nothing.
        fake_encoder("Explique energia solar", UNRELATED)

        assert _names("Explique energia solar") == set()

    def test_lexical_matches_are_never_dropped(self, fake_encoder):
        # The ranker is useless here (everything scores 0), so the keyword match
        # is the only thing that can keep this tool available.
        assert "listar_arquivos" in _lexical_names("liste os arquivos")

        fake_encoder("liste os arquivos", UNRELATED)

        assert "listar_arquivos" in _names("liste os arquivos")

    def test_top_k_bounds_the_semantic_contribution(self, fake_encoder, agent_settings, monkeypatch):
        # Every tool scores 1.0, so only the cap can hold this back. The lexical
        # hit is additive and outside the cap, hence the union is top_k + 1.
        fake_encoder("liste os documentos do cliente", DOCUMENTS)
        monkeypatch.setattr(agent_settings, "tool_retrieval_top_k", 4)

        names = _names("liste os documentos do cliente")

        assert len(names - _lexical_names("liste os documentos do cliente")) <= 4
        assert len(names) < len(REGISTRO_FERRAMENTAS)

    def test_operational_request_without_any_signal_gets_the_floor(self, fake_encoder):
        # "componentes" is a known domain noun but appears in no tool keyword
        # list, and the encoder is orthogonal to every tool.
        assert _lexical_names("quais componentes temos") == set()

        fake_encoder("quais componentes temos", UNRELATED)

        assert _names("quais componentes temos") == set(READ_CORE)

    def test_floor_is_never_applied_to_a_general_question(self, fake_encoder):
        fake_encoder("Explique energia solar", UNRELATED)

        assert _names("Explique energia solar") == set()

    def test_pedagogical_request_keeps_the_business_report_out(self, fake_encoder):
        # Maximum similarity for the business report generator would otherwise
        # expose it, but it answers stock/CRM data, not school documents.
        fake_encoder("Gere um relatorio pedagogico PEI do aluno", SCHOOL)

        names = _names("Gere um relatorio pedagogico PEI do aluno")

        assert "gerar_documento_local" in names
        assert "gerar_relatorio_local" not in names

    def test_attachment_discards_still_win_over_retrieval(self, fake_encoder):
        # processar_arquivo is deliberately dropped for an already-extracted
        # attachment, even when the ranker wants it.
        fake_encoder("liste os documentos", DOCUMENTS)

        names = _names("liste os documentos", has_document=True)

        assert "processar_arquivo" not in names


class TestCaching:
    def test_static_tool_embeddings_are_encoded_once(self, fake_encoder):
        encoder = fake_encoder("quais documentos eu tenho", DOCUMENTS)

        ai_react._filtrar_ferramentas("quais documentos eu tenho")
        ai_react._filtrar_ferramentas("qual o estoque de parafusos")
        ai_react._filtrar_ferramentas("meus clientes")

        batches_com_todas = [b for b in encoder.batches if len(b) == len(REGISTRO_FERRAMENTAS)]
        assert len(batches_com_todas) == 1

    def test_reset_clears_the_cache(self, fake_encoder):
        encoder = fake_encoder("quais documentos eu tenho", DOCUMENTS)
        ai_react._filtrar_ferramentas("quais documentos eu tenho")

        tool_retrieval.reset_tool_embeddings()
        ai_react._filtrar_ferramentas("quais documentos eu tenho")

        batches_com_todas = [b for b in encoder.batches if len(b) == len(REGISTRO_FERRAMENTAS)]
        assert len(batches_com_todas) == 2

    def test_missing_encoder_degrades_to_the_lexical_path(self, monkeypatch):
        monkeypatch.setattr(tool_retrieval, "get_embedding_model", lambda: None)
        pergunta = "Gere um relatorio do estoque em PDF"

        assert _names(pergunta) == _lexical_names(pergunta)

    def test_disabling_retrieval_restores_lexical_only(self, fake_encoder, agent_settings, monkeypatch):
        fake_encoder("quais documentos eu tenho", DOCUMENTS)
        monkeypatch.setattr(agent_settings, "tool_retrieval_enabled", False)

        names = _names("quais documentos eu tenho")

        assert "listar_documentos_rag" not in names
        assert names == _lexical_names("quais documentos eu tenho")


class TestRanking:
    def test_top_tools_orders_by_score(self):
        scores = {"a": 0.9, "b": 0.5, "c": 0.1}

        assert [nome for nome, _ in tool_retrieval.top_tools(scores, top_k=10, min_score=0.3)] == [
            "a",
            "b",
        ]

    def test_top_tools_respects_an_explicit_cap(self):
        scores = {f"t{index}": 0.9 for index in range(20)}

        assert len(tool_retrieval.top_tools(scores, top_k=3, min_score=0.0)) == 3

    def test_top_tools_drops_everything_below_the_floor(self):
        scores = {"a": 0.2, "b": 0.1}

        assert tool_retrieval.top_tools(scores, top_k=10, min_score=0.34) == []

    def test_top_tools_of_nothing_is_empty(self):
        assert tool_retrieval.top_tools(None) == []
        assert tool_retrieval.top_tools({}) == []
