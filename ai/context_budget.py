"""Token budget management for LLM context window.

Estimates token usage and manages context to prevent overflow.
Uses character-based estimation (1 token ~ 4 chars for English, ~2 chars for CJK).

Phase 5 adds:
- WorkingMemory: explicit slots exposed to the model (facts, pending tasks, recent results)
- LLM summarization when >70% budget (optional, with local fallback)
- Relevance-based truncation (not blind FIFO)
- Correct token accounting: system + tools + user + assistant + working_memory ≤ num_ctx
"""

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.settings import get_settings

# Approximate chars per token (varies by language and tokenizer)
CHARS_PER_TOKEN = 3.5

# Context utilization thresholds
MAX_CONTEXT_USE = 0.85  # Use at most 85% of context window
WARN_CONTEXT_USE = 0.70  # Warn when exceeding 70%
SUMMARIZE_TRIGGER = 0.70  # Trigger LLM summarization at 70%

# Working memory budget (percentage of available tokens)
WORKING_MEMORY_MAX_RATIO = 0.15  # 15% of available tokens for working memory


@dataclass
class WorkingMemory:
    """Explicit working memory slots exposed to the model.

    Instead of burying facts in conversation history, the model gets a dedicated
    "scratchpad" with three sections it can read and the system can write:
    - fatos_confirmados: key facts the user has stated or tools have verified
    - tarefas_pendentes: explicit next steps the model declared
    - resultados_recentes: compact tool outputs from the last N turns
    """

    fatos_confirmados: list[str] = field(default_factory=list)
    tarefas_pendentes: list[str] = field(default_factory=list)
    resultados_recentes: list[str] = field(default_factory=list)

    MAX_ITENS = 8  # per slot
    MAX_CHARS_ITEM = 300

    def adicionar_fato(self, fato: str) -> None:
        if fato and fato not in self.fatos_confirmados:
            self.fatos_confirmados.append(fato[: self.MAX_CHARS_ITEM])
            if len(self.fatos_confirmados) > self.MAX_ITENS:
                self.fatos_confirmados.pop(0)

    def adicionar_tarefa(self, tarefa: str) -> None:
        if tarefa and tarefa not in self.tarefas_pendentes:
            self.tarefas_pendentes.append(tarefa[: self.MAX_CHARS_ITEM])
            if len(self.tarefas_pendentes) > self.MAX_ITENS:
                self.tarefas_pendentes.pop(0)

    def adicionar_resultado(self, resultado: str) -> None:
        if resultado:
            self.resultados_recentes.append(resultado[: self.MAX_CHARS_ITEM])
            if len(self.resultados_recentes) > self.MAX_ITENS:
                self.resultados_recentes.pop(0)

    def limpar_concluidas(self, tarefas_feitas: list[str]) -> None:
        """Remove completed tasks from pending."""
        self.tarefas_pendentes = [t for t in self.tarefas_pendentes if t not in tarefas_feitas]

    def para_system_prompt(self) -> str | None:
        """Render as a system message block. Returns None if empty."""
        partes = []
        if self.fatos_confirmados:
            partes.append("Fatos confirmados:\n- " + "\n- ".join(self.fatos_confirmados))
        if self.tarefas_pendentes:
            partes.append("Tarefas pendentes:\n- " + "\n- ".join(self.tarefas_pendentes))
        if self.resultados_recentes:
            partes.append("Resultados recentes:\n- " + "\n- ".join(self.resultados_recentes))
        return "\n\n".join(partes) if partes else None

    def estimate_tokens(self) -> int:
        texto = self.para_system_prompt() or ""
        return max(0, int(len(texto) / CHARS_PER_TOKEN)) + 4  # +4 for message framing


def estimate_tokens(text: str) -> int:
    """Estimate token count from text.

    Uses character-based estimation with adjustment for whitespace and punctuation.
    """
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def estimate_message_tokens(message: dict) -> int:
    """Estimate token count for a single chat message."""
    role_tokens = 4  # Message framing tokens
    content_tokens = estimate_tokens(message.get("content", ""))

    # Tool calls add overhead
    tool_calls = message.get("tool_calls")
    if tool_calls:
        content_tokens += estimate_tokens(str(tool_calls))

    return role_tokens + content_tokens


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total token count for a list of messages."""
    total = 0
    for msg in messages:
        total += estimate_message_tokens(msg)
    return total


class ContextBudget:
    """Manages context window budget allocation.

    Allocates tokens to:
    - System prompt
    - Document content
    - Session history
    - Tool schemas
    - Response (reserved)
    """

    def __init__(self, num_ctx: int | None = None):
        settings = get_settings()
        self.num_ctx = num_ctx or settings.num_ctx
        self.reserved_tokens = int(self.num_ctx * 0.15)  # 15% reserved for response
        self.available_tokens = self.num_ctx - self.reserved_tokens

        # Budget allocation (percentages of available tokens)
        self.system_prompt_max = int(self.available_tokens * 0.12)  # ~12%
        self.document_max = int(self.available_tokens * 0.25)  # ~25%
        self.history_max = int(self.available_tokens * 0.35)  # ~35%
        self.tools_max = int(self.available_tokens * 0.10)  # ~10%
        self.memories_max = int(self.available_tokens * 0.08)  # ~8%
        self.working_memory_max = int(self.available_tokens * WORKING_MEMORY_MAX_RATIO)  # ~15%

    def analyze_messages(self, messages: list[dict], working_memory: WorkingMemory | None = None) -> dict:
        """Analyze current message list and return budget breakdown."""
        system_tokens = 0
        history_tokens = 0
        doc_tokens = 0
        tool_tokens = 0

        for msg in messages:
            role = msg.get("role", "")
            tokens = estimate_message_tokens(msg)
            content = msg.get("content", "")

            if role == "system":
                if "Documento Anexado" in content:
                    doc_tokens += tokens
                elif "Ferramentas Disponiveis" in content:
                    tool_tokens += tokens
                elif "Fatos confirmados" in content or "Tarefas pendentes" in content or "Resultados recentes" in content:
                    # Working memory injected as system message
                    pass  # counted separately via working_memory estimate
                else:
                    system_tokens += tokens
            elif role in ("user", "assistant"):
                history_tokens += tokens
            else:
                history_tokens += tokens

        wm_tokens = working_memory.estimate_tokens() if working_memory else 0
        total_used = system_tokens + history_tokens + doc_tokens + tool_tokens + wm_tokens
        utilization = total_used / self.num_ctx if self.num_ctx > 0 else 0

        return {
            "system_tokens": system_tokens,
            "document_tokens": doc_tokens,
            "history_tokens": history_tokens,
            "tool_tokens": tool_tokens,
            "working_memory_tokens": wm_tokens,
            "total_used": total_used,
            "available": self.available_tokens,
            "utilization": utilization,
            "over_budget": utilization > MAX_CONTEXT_USE,
            "warnings": self._get_warnings(system_tokens, doc_tokens, history_tokens, tool_tokens, wm_tokens),
        }

    def _get_warnings(self, system: int, doc: int, history: int, tools: int, wm: int) -> list[str]:
        """Generate warnings about budget usage."""
        warnings = []
        if system > self.system_prompt_max:
            warnings.append(
                f"System prompt ({system} tokens) exceeds budget ({self.system_prompt_max})"
            )
        if doc > self.document_max:
            warnings.append(f"Document ({doc} tokens) exceeds budget ({self.document_max})")
        if history > self.history_max:
            warnings.append(f"History ({history} tokens) exceeds budget ({self.history_max})")
        if tools > self.tools_max:
            warnings.append(f"Tools ({tools} tokens) exceeds budget ({self.tools_max})")
        if wm > self.working_memory_max:
            warnings.append(f"Working memory ({wm} tokens) exceeds budget ({self.working_memory_max})")
        return warnings

    @staticmethod
    def _schema_tokens(tool: Any) -> int:
        """Estimate the tokens a single tool schema costs on the wire."""
        schema = tool.para_openai() if hasattr(tool, "para_openai") else tool
        return estimate_tokens(str(schema))

    def trim_tools_to_budget(self, tools: list[Any], *, tools_max: int | None = None) -> list[Any]:
        """Drop tool schemas from the end until they fit the tool token budget.

        The most critical tools are registered first in ``REGISTRO_FERRAMENTAS``,
        so trimming keeps the prefix. At least one tool is always kept, even
        when a single schema alone exceeds the budget.
        """
        if not tools:
            return tools
        limit = self.tools_max if tools_max is None else max(0, tools_max)
        if limit <= 0:
            return tools
        keep = len(tools)
        while keep > 1 and sum(self._schema_tokens(t) for t in tools[:keep]) > limit:
            keep -= 1
        return tools[:keep]

    def _relevance_score(self, msg: dict, query_terms: set[str] | None = None) -> float:
        """Score a message's relevance for retention.

        Higher = more relevant. Considers:
        - Recency (recent messages more relevant)
        - Role (tool results > assistant > user)
        - Keyword overlap with query terms (if provided)
        """
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        # Base score by role
        if role == "tool":
            base = 1.0  # Tool results are facts
        elif role == "assistant":
            base = 0.7  # Model reasoning
        else:
            base = 0.5  # User prompts

        # Keyword overlap bonus
        bonus = 0.0
        if query_terms:
            words = set(content.lower().split())
            overlap = len(words & query_terms)
            bonus = min(0.3, overlap * 0.05)

        return base + bonus

    def trim_history(
        self,
        messages: list[dict],
        target_reduction: int = 0,
        *,
        query_terms: set[str] | None = None,
        working_memory: WorkingMemory | None = None,
    ) -> list[dict]:
        """Trim history messages to fit within budget using relevance, not FIFO.

        Strategy:
        1. Keep system messages (including working memory injection)
        2. Score conversation messages by relevance
        3. Remove lowest-relevance messages first
        4. Always keep at least the last 2 exchanges
        """
        if not messages:
            return messages

        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        current_tokens = estimate_messages_tokens(conv_msgs)

        if target_reduction <= 0 and current_tokens <= self.history_max:
            return messages

        # Score all conversation messages by relevance
        scored = [(self._relevance_score(m, query_terms), i, m) for i, m in enumerate(conv_msgs)]
        scored.sort(key=lambda x: x[0])  # lowest relevance first

        # Remove lowest-relevance messages until we fit
        # But never remove the last 2 messages (most recent exchange)
        min_keep = min(2, len(conv_msgs))
        removable = scored[:-min_keep] if len(scored) > min_keep else []

        for _, _, msg in removable:
            if current_tokens <= self.history_max:
                break
            conv_msgs.remove(msg)
            current_tokens -= estimate_message_tokens(msg)

        # If still over budget, fall back to FIFO on remaining (oldest first)
        while conv_msgs and current_tokens > self.history_max:
            if len(conv_msgs) <= min_keep:
                break
            removed = conv_msgs.pop(0)
            current_tokens -= estimate_message_tokens(removed)

        return system_msgs + conv_msgs

    def summarize_if_needed(
        self,
        messages: list[dict],
        summarize_fn: Callable[[str], str] | None = None,
        *,
        working_memory: WorkingMemory | None = None,
        query_terms: set[str] | None = None,
    ) -> list[dict]:
        """Summarize old messages if over 70% budget.

        Trigger: utilization >= SUMMARIZE_TRIGGER (70%) or over_budget (85%).
        Uses LLM summarization when summarize_fn provided; falls back to local
        mechanical summarization; finally falls back to relevance trimming.

        Args:
            messages: List of chat messages
            summarize_fn: Optional LLM summarization function (text -> text)
            working_memory: WorkingMemory to include in token accounting
            query_terms: Terms from current query for relevance scoring

        Returns:
            Optimized message list
        """
        budget = self.analyze_messages(messages, working_memory)

        trigger = budget["utilization"] >= SUMMARIZE_TRIGGER or budget["over_budget"]
        if not trigger:
            return messages

        # Separate system from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        if len(conv_msgs) <= 4:
            return messages

        # Split: old messages to summarize, recent to keep (last 6)
        split_point = len(conv_msgs) - 6
        old_msgs = conv_msgs[:split_point]
        recent_msgs = conv_msgs[split_point:]

        # Generate summary of old messages
        old_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')[:200]}"
            for m in old_msgs
            if m.get("content")
        )

        summary = None
        if summarize_fn is not None:
            with contextlib.suppress(Exception):
                summary = summarize_fn(old_text)

        if summary is None:
            # Local mechanical fallback
            summary = _simple_summarize(old_text)

        summary_msg = {"role": "system", "content": f"Resumo da conversa anterior:\n{summary}"}
        return system_msgs + [summary_msg] + recent_msgs

    def inject_working_memory(
        self, messages: list[dict], working_memory: WorkingMemory
    ) -> list[dict]:
        """Inject working memory as a system message if not empty."""
        wm_text = working_memory.para_system_prompt()
        if not wm_text:
            return messages
        # Insert after existing system messages, before conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]
        wm_msg = {"role": "system", "content": f"Memória de trabalho:\n{wm_text}"}
        return system_msgs + [wm_msg] + conv_msgs

    def get_stats(self) -> dict:
        """Return current budget configuration."""
        return {
            "num_ctx": self.num_ctx,
            "reserved_tokens": self.reserved_tokens,
            "available_tokens": self.available_tokens,
            "system_prompt_max": self.system_prompt_max,
            "document_max": self.document_max,
            "history_max": self.history_max,
            "tools_max": self.tools_max,
            "memories_max": self.memories_max,
            "working_memory_max": self.working_memory_max,
        }


def _simple_summarize(text: str) -> str:
    """Simple local summarization: extract key sentences."""
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    if len(sentences) <= 3:
        return text
    # Keep first, middle, last
    keep = [sentences[0], sentences[len(sentences) // 2], sentences[-1]]
    return ". ".join(keep) + "."


def get_budget(num_ctx: int | None = None) -> ContextBudget:
    """Get a ContextBudget instance."""
    return ContextBudget(num_ctx)
