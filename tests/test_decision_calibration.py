"""Tests for decision-layer calibration tooling (DECISION_LAYER.md §9)."""

import json
from types import SimpleNamespace

import pytest

from core.decision_calibration import (
    DecisionRecorder,
    accuracy,
    balanced_accuracy,
    default_outcomes_path,
    load_outcomes,
    recommend_guard_threshold,
    recommend_score_threshold,
    report_pretty,
    summarize_outcomes,
)
from core.decisions import (
    DecisionClient,
    DecisionLayerSettings,
    NoulAnswer,
    ScoreAnswer,
    decide_keep_chunk,
    decide_tool_guard,
    get_decision_client,
    reset_decision_client,
)


class TestDecisionRecorder:
    def test_appends_and_loads_roundtrip(self, tmp_path):
        recorder = DecisionRecorder(tmp_path / "outcomes.jsonl")
        recorder.append({"kind": "tool_guard", "tool": "enviar_email", "value": 0.8})
        recorder.append({"kind": "rag_gate", "keep": True})

        entries = load_outcomes(recorder.path)
        assert len(entries) == 2
        assert entries[0]["tool"] == "enviar_email"
        assert entries[1]["kind"] == "rag_gate"

    def test_creates_parent_directory(self, tmp_path):
        recorder = DecisionRecorder(tmp_path / "nested" / "outcomes.jsonl")
        recorder.append({"kind": "probe"})
        assert (tmp_path / "nested" / "outcomes.jsonl").is_file()

    def test_loads_skips_corrupt_lines(self, tmp_path):
        path = tmp_path / "outcomes.jsonl"
        path.write_text('{"kind": "ok"}\n{corrupto\n{"kind": "outro"}\n', encoding="utf-8")
        entries = load_outcomes(path)
        assert [e.get("kind") for e in entries] == ["ok", "outro"]

    def test_append_never_raises_on_bad_path(self, tmp_path):
        recorder = DecisionRecorder(tmp_path / "x" / "y" / "out.jsonl")
        recorder.append({"kind": "pode-falhar"})
        assert True


class TestAccuracyMetrics:
    def test_accuracy_perfect_split(self):
        entries = [
            {"label": 1, "probability": 0.9},
            {"label": 1, "probability": 0.8},
            {"label": 0, "probability": 0.2},
            {"label": 0, "probability": 0.1},
        ]
        assert accuracy(entries, threshold=0.5) == 1.0
        assert accuracy(entries, threshold=0.85) == 0.75

    def test_balanced_accuracy_ignores_imbalance(self):
        entries = [{"label": 1, "probability": 0.9}] + [
            {"label": 0, "probability": 0.1} for _ in range(9)
        ]
        assert balanced_accuracy(entries, threshold=0.5) == 1.0

    def test_empty_entries_score_zero(self):
        assert accuracy([], threshold=0.5) == 0.0
        assert balanced_accuracy([], threshold=0.5) == 0.0


class TestThresholdRecommendations:
    def test_guard_threshold_finds_separation(self):
        entries = [{"label": 1, "probability": 0.95}, {"label": 1, "probability": 0.88}] + [
            {"label": 0, "probability": 0.10},
            {"label": 0, "probability": 0.22},
        ]
        report = recommend_guard_threshold(entries)
        assert report.balanced_accuracy == 1.0
        assert 0.30 < report.threshold <= 0.85
        assert report.n == 4
        assert report.n_positive == 2
        assert report.n_negative == 2

    def test_guard_threshold_uses_custom_grid(self):
        entries = [
            {"label": 1, "probability": 0.90},
            {"label": 0, "probability": 0.10},
        ]
        report = recommend_guard_threshold(entries, grid=(0.6, 0.7, 0.8))
        assert report.threshold in (0.6, 0.7, 0.8)
        assert report.grid == (0.6, 0.7, 0.8)

    def test_score_threshold_recommendation(self):
        entries = [
            {"label": 1, "normalized": 0.85},
            {"label": 1, "normalized": 0.70},
            {"label": 0, "normalized": 0.20},
        ]
        report = recommend_score_threshold(entries)
        assert report.kind == "rag_score"
        assert report.balanced_accuracy == 1.0
        assert report.as_dict()["n"] == 3

    def test_report_pretty_renders(self):
        report = recommend_guard_threshold(
            [{"label": 1, "probability": 0.9}, {"label": 0, "probability": 0.1}]
        )
        rendered = report_pretty(report)
        assert "threshold sugerido" in rendered
        assert str(report.threshold) in rendered

    def test_summarize_outcomes_rolls_up_rates(self):
        entries = [
            {"kind": "tool_guard", "predicted": True, "value": 0.9},
            {"kind": "tool_guard", "predicted": False, "value": 0.1},
            {"kind": "rag_gate", "predicted": False, "value": 0.2},
        ]
        summary = summarize_outcomes(entries)
        assert summary["tool_guard"]["n"] == 2
        assert summary["tool_guard"]["rate"] == 0.5
        assert summary["rag_gate"]["predicted_true"] == 0
        assert summary["rag_gate"]["mean_value"] == 0.2

    def test_summarize_outcomes_empty(self):
        assert summarize_outcomes([]) == {}


class TestOutcomeWiring:
    def _enabled_client(self, tmp_path, *, provider=None):
        settings = DecisionLayerSettings(enabled=True, record_outcomes=True)
        if provider is None:
            provider = _noul_provider(0.90)
        recorder = DecisionRecorder(tmp_path / "outcomes.jsonl")
        return DecisionClient(settings, provider=provider, recorder=recorder)

    def test_tool_guard_records_outcome(self, tmp_path):
        client = self._enabled_client(tmp_path)
        gate = decide_tool_guard(
            client,
            client._settings,
            tool="apagar_arquivo",
            arguments={"path": "/tmp/x"},
        )
        assert gate.requires_approval is True

        entries = load_outcomes(tmp_path / "outcomes.jsonl")
        assert [e["kind"] for e in entries] == ["tool_guard"]
        assert entries[0]["tool"] == "apagar_arquivo"
        assert entries[0]["value"] == pytest.approx(0.90)
        assert entries[0]["decision"] == "requires_approval"

    def test_rag_gate_records_outcome(self, tmp_path):
        provider = _score_provider(2.0)
        client = self._enabled_client(tmp_path, provider=provider)
        assert (
            decide_keep_chunk(client, client._settings, query="fat", chunk="trecho enorme") is True
        )

        entries = load_outcomes(tmp_path / "outcomes.jsonl")
        assert entries[0]["kind"] == "rag_gate"
        assert entries[0]["decision"] == "keep"
        assert entries[0]["score"] == 2.0

    def test_disabled_layer_never_records(self, tmp_path):
        settings = DecisionLayerSettings(enabled=False)
        recorder = DecisionRecorder(tmp_path / "outcomes.jsonl")
        client = DecisionClient(settings, provider=_noul_provider(0.99), recorder=recorder)

        gate = decide_tool_guard(client, settings, tool="apagar_arquivo", arguments={})
        assert gate.requires_approval is False
        assert not recorder.path.exists()

    def test_pure_client_record_noops_when_disabled(self, tmp_path):
        recorder = DecisionRecorder(tmp_path / "outcomes.jsonl")
        client = DecisionClient(DecisionLayerSettings(enabled=False), recorder=recorder)
        client.record({"kind": "probe"})
        assert not recorder.path.exists()

    def test_get_decision_client_builds_recorder_only_when_enabled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "core.decision_calibration.get_settings",
            lambda: SimpleNamespace(logs_dir=tmp_path),
        )
        monkeypatch.setattr(
            "core.decisions.get_settings",
            lambda: SimpleNamespace(
                decision=DecisionLayerSettings(enabled=True, record_outcomes=True)
            ),
        )
        reset_decision_client()
        client = get_decision_client()
        assert client._recorder is not None
        assert client._recorder.path == tmp_path / "decision_outcomes.jsonl"
        reset_decision_client()

    def test_default_outcomes_path_uses_logs_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "core.decision_calibration.get_settings",
            lambda: SimpleNamespace(logs_dir=tmp_path),
        )
        assert default_outcomes_path() == tmp_path / "decision_outcomes.jsonl"


def _noul_provider(value: float):
    return _StubProvider(
        {
            "altera_dados": NoulAnswer(noul=value),
            "irreversivel": NoulAnswer(noul=value),
            "rede": NoulAnswer(noul=value),
            "destrutiva": NoulAnswer(noul=value),
        }
    )


def _score_provider(score: float):
    return _StubProvider({"relevancia": ScoreAnswer(score=score)})


class _StubProvider:
    def __init__(self, answers):
        self._answers = answers

    def decide(self, request, *, timeout_ms):
        return self._answers
