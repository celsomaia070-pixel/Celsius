"""Map extracted source values onto target form fields.

Matching is deterministic and conservative: exact normalised label, then
containment, then token overlap.  Anything weaker is left to the LLM, and
whatever stays unresolved is reported rather than guessed.
"""

from __future__ import annotations

from typing import Any

from core.document_forms import FormField, _clean, _fold, _normalized

_ALIASES = {
    "nome": "nome pessoa", "nome do aluno": "nome pessoa", "nome da crianca": "nome pessoa",
    "nome do estudante": "nome pessoa", "aluno": "nome pessoa", "estudante": "nome pessoa",
    "data de nascimento": "nascimento", "nascimento": "nascimento",
    "escola": "escola", "unidade escolar": "escola",
}
_STOPWORDS = frozenset(
    {
        "a", "as", "o", "os", "da", "das", "de", "do", "dos", "e", "em", "no", "na",
        "nos", "nas", "por", "para", "com", "que", "se", "ou", "um", "uma", "the", "of",
    }
)


def _tokens(value: str) -> set[str]:
    return {word for word in _normalized(value).split() if word not in _STOPWORDS}


def _score(field: FormField, source_key: str, source_value: str) -> float:
    label_key = _normalized(field.label)
    if not label_key:
        return 0.0
    if label_key == source_key:
        return 1.0
    if label_key in _ALIASES and _ALIASES[label_key] == _ALIASES.get(source_key):
        return 0.96
    # "Unidade Escolar" should accept a source labelled "Escola".
    if label_key in source_key or source_key in label_key:
        shorter, longer = sorted((len(label_key), len(source_key)))[0], sorted(
            (len(label_key), len(source_key))
        )[1]
        if shorter >= 4 and shorter / longer >= 0.5:
            return 0.9
    field_tokens = _tokens(field.label)
    source_tokens = _tokens(source_key)
    if not field_tokens or not source_tokens:
        return 0.0
    shared = field_tokens & source_tokens
    if not shared:
        return 0.0
    # Cover the field label first, then the source key: a field matched by a long
    # unrelated source label must not win over an exact-ish match.
    return 0.6 * len(shared) / len(field_tokens) + 0.4 * len(shared) / len(source_tokens)


def match_values_to_fields(
    fields: list[FormField],
    values: dict[str, str],
    *,
    min_confidence: float = 0.90,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Return ``{field label: value}`` for confident matches plus a review list.

    Each target field is filled at most once, so when two source labels could
    claim the same field the best-scoring one wins and the loser is reported.
    """

    scored: list[tuple[float, str, FormField, str]] = []
    for field in fields:
        if not field.label:
            continue
        for source_key, source_value in values.items():
            value = _clean(source_value)
            if not value:
                continue
            score = _score(field, _normalized(source_key), value)
            if score >= min_confidence:
                scored.append((score, source_key, field, value))

    # Highest score first; ties resolve on the field label for stable output.
    scored.sort(key=lambda item: (-item[0], item[2].label, item[1]))

    chosen: dict[str, dict[str, Any]] = {}
    losers: list[dict[str, Any]] = []
    for score, source_key, field, value in scored:
        label = field.label
        if label in chosen:
            if chosen[label]["value"] != value:
                losers.append(
                    {
                        "field": label,
                        "candidate_value": value,
                        "from": source_key,
                        "score": round(score, 3),
                        "reason": "outro valor tambem corresponde a este campo",
                    }
                )
            continue
        chosen[label] = {"value": value, "from": source_key, "score": round(score, 3)}

    # Competing values with near-equal scores are a conflict, never an arbitrary winner.
    ambiguous = {
        item["field"] for item in losers
        if chosen[item["field"]]["score"] - item["score"] < 0.10
    }
    resolved = {label: item["value"] for label, item in chosen.items() if label not in ambiguous}
    report = [
        {
            "field": label,
            "value": item["value"],
            "from": item["from"],
            "score": item["score"],
            "status": "needs_review" if label in ambiguous else "accepted",
        }
        for label, item in sorted(chosen.items())
    ]
    return resolved, report + losers


def resolve_checkbox_values(
    fields: list[FormField],
    values: dict[str, str],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Coerce free text into the exact caption of a checkbox option.

    A checkbox can only be marked with "X", so the value has to name an option the
    scanner actually found. Sources normally label the answer ("Tipo de
    Atendimento: Sala Multifuncional"), but a report may also just state the
    answer, so an unlabelled value is accepted when it matches exactly one option
    of exactly one field. Anything vaguer is reported, never guessed.
    """

    def option_for(value: str, field: FormField) -> tuple[str | None, list[str]]:
        wanted = _fold(value)
        if not wanted:
            return None, []
        keys = {option: _fold(option) for option in field.options}
        exact = [option for option, key in keys.items() if key == wanted]
        if exact:
            return exact[0], []
        contained = [option for option, key in keys.items() if key and (wanted in key or key in wanted)]
        if len(contained) == 1:
            return contained[0], []
        return None, contained

    resolved: dict[str, str] = {}
    ambiguous: list[dict[str, str]] = []
    groups = [field for field in fields if field.kind == "checkbox" and field.options]
    claimed: dict[str, str] = {}

    # Pass 1: prefer a value that names the field outright.
    for field in groups:
        label_key = _normalized(field.label)
        raw = next(
            (
                value
                for key, value in values.items()
                if _normalized(key) == label_key or _normalized(key) in label_key
            ),
            None,
        )
        if raw is None:
            continue
        option, contained = option_for(raw, field)
        if option:
            resolved[field.label] = option
            claimed.setdefault(_fold(raw), field.label)
        else:
            ambiguous.append(
                {
                    "field": field.label,
                    "value": raw,
                    "reason": (
                        f"o texto corresponde a varias opcoes: {', '.join(contained)}"
                        if contained
                        else "nenhuma opcao marcada corresponde ao texto informado"
                    ),
                }
            )

    # Pass 2: an unlabelled answer is usable only if it identifies one option
    # across the whole form, otherwise it could belong to any group.
    for key, value in values.items():
        if key in resolved or _fold(value) in claimed:
            continue
        matches = [
            (field, option_for(value, field)[0])
            for field in groups
            if field.label not in resolved
        ]
        hits = [(field, option) for field, option in matches if option]
        if len(hits) == 1:
            field, option = hits[0]
            resolved[field.label] = option
            claimed[_fold(value)] = field.label
        elif len(hits) > 1:
            ambiguous.append(
                {
                    "field": key,
                    "value": value,
                    "reason": "o mesmo texto serve a mais de um grupo: "
                    + ", ".join(item.label for item, _ in hits),
                }
            )
    return resolved, ambiguous


def unmapped_fields(fields: list[FormField], resolved: dict[str, str]) -> list[str]:
    return [field.label for field in fields if field.label and field.label not in resolved]
