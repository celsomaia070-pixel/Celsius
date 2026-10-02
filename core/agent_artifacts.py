"""Task workspaces and deterministic artifact verification.

Agents may describe success incorrectly.  This module makes produced files first
class task evidence: every task has an isolated workspace, an inventory with
hashes, and a small deterministic verification report saved in the checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

_MAX_HASH_BYTES = 64 * 1024 * 1024
_MAX_TEXT_PREVIEW = 2_000
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|\.?[\\/])[^\n\r<>|?*]+\.(?:txt|md|json|csv|pdf|docx|xlsx|png|jpg|jpeg|svg|html|py)",
    re.I,
)


def task_requests_artifact(task: dict[str, Any]) -> bool:
    """Whether the objective promises a file rather than only an answer in chat."""

    objective = str(task.get("objective") or "").casefold()
    makes_file = re.search(
        r"\b(?:ger\w*|cri\w*|produz\w*|emit\w*|elabor\w*|preench\w*|complet\w*)\b", objective
    )
    artifact = re.search(
        r"\b(?:relat[oó]rio|documento|arquivo|pdf|docx|pei|paee|formul[aá]rio)\b", objective
    )
    return bool(makes_file and artifact)


def workspace_for(data_dir: Path, task_id: str) -> Path:
    """Return and create the only task-owned output directory."""
    root = Path(data_dir).resolve() / "agent_workspaces"
    path = (root / task_id).resolve()
    if path.parent != root:
        raise ValueError("Identificador de tarefa invalido.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, *, root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if path.is_relative_to(root) else path.name,
        "size_bytes": path.stat().st_size,
        "extension": path.suffix.lower(),
        "exists": path.is_file(),
    }
    if item["exists"] and item["size_bytes"] <= _MAX_HASH_BYTES:
        item["sha256"] = _digest(path)
    if item["exists"] and path.suffix.lower() in {".txt", ".md", ".json", ".csv", ".py", ".html"}:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            item["text_preview"] = text[:_MAX_TEXT_PREVIEW]
            item["nonempty"] = bool(text.strip())
            if path.suffix.lower() == ".json":
                json.loads(text)
                item["valid_json"] = True
        except (OSError, ValueError, UnicodeError):
            item["valid_json"] = False
    return item


def collect_artifacts(task: dict[str, Any], data_dir: Path) -> list[dict[str, Any]]:
    """Collect files from the isolated workspace and trusted tool-result paths."""
    workspace = workspace_for(data_dir, str(task["id"]))
    input_root = workspace / "inputs"
    candidates = {
        path.resolve()
        for path in workspace.rglob("*")
        if path.is_file() and not path.resolve().is_relative_to(input_root)
    }
    base = Path(data_dir).parent.resolve()
    for step in task.get("steps", []):
        result_text = str(step.get("result", ""))
        if step.get("tool") in {
            "inspecionar_formulario_documento",
            "preencher_documento",
            "preencher_documento_com_fontes",
            "gerar_documento_local",
        }:
            # Document results also contain source/evidence paths. Only the
            # confirmed written output is an artifact, never an input or preview.
            try:
                payload, _ = json.JSONDecoder().raw_decode(result_text.lstrip())
            except (ValueError, TypeError):
                continue
            paths = (
                [payload["output"]]
                if isinstance(payload, dict)
                and payload.get("written") is True
                and isinstance(payload.get("output"), str)
                and payload["output"]
                else []
            )
        else:
            paths = _PATH_RE.findall(result_text)
        for raw in paths:
            try:
                candidate = Path(raw.strip(" .,:;()[]{}\"'"))
                if not candidate.is_absolute():
                    candidate = base / candidate
                candidate = candidate.resolve()
                if candidate.is_relative_to(input_root):
                    continue
                if candidate.is_file() and (
                    candidate.is_relative_to(base) or candidate.is_relative_to(workspace)
                ):
                    candidates.add(candidate)
            except (OSError, ValueError):
                continue
    return [_artifact(path, root=workspace) for path in sorted(candidates)]


def verify_task(task: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    """Create evidence used by UI/API; no LLM is involved in this decision."""
    artifacts = collect_artifacts(task, data_dir)
    problems: list[str] = []
    for artifact in artifacts:
        if not artifact["exists"] or artifact["size_bytes"] == 0:
            problems.append(f"Arquivo vazio ou ausente: {artifact['path']}")
        if artifact.get("valid_json") is False:
            problems.append(f"JSON invalido: {artifact['path']}")
    return {
        "checked": True,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "passed": not problems,
        "problems": problems,
    }
