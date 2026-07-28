"""Token budget management for LLM context window.

Estimates token usage and manages context to prevent overflow.
Uses character-based estimation (1 token ~ 4 chars for English, ~2 chars for CJK).
"""

from core.settings import get_settings

# Approximate chars per token (varies by language and tokenizer)
CHARS_PER_TOKEN = 3.5

# Context utilization thresholds
MAX_CONTEXT_USE = 0.85  # Use at most 85% of context window
WARN_CONTEXT_USE = 0.70  # Warn when exceeding 70%


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
        self.system_prompt_max = int(self.available_tokens * 0.15)  # ~15%
        self.document_max = int(self.available_tokens * 0.25)  # ~25%
        self.history_max = int(self.available_tokens * 0.40)  # ~40%
        self.tools_max = int(self.available_tokens * 0.10)  # ~10%
        self.memories_max = int(self.available_tokens * 0.10)  # ~10%

    def analyze_messages(self, messages: list[dict]) -> dict:
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
                else:
                    system_tokens += tokens
            elif role in ("user", "assistant"):
                history_tokens += tokens
            else:
                history_tokens += tokens

        total_used = system_tokens + history_tokens + doc_tokens + tool_tokens
        utilization = total_used / self.num_ctx if self.num_ctx > 0 else 0

        return {
            "system_tokens": system_tokens,
            "document_tokens": doc_tokens,
            "history_tokens": history_tokens,
            "tool_tokens": tool_tokens,
            "total_used": total_used,
            "available": self.available_tokens,
            "utilization": utilization,
            "over_budget": utilization > MAX_CONTEXT_USE,
            "warnings": self._get_warnings(system_tokens, doc_tokens, history_tokens, tool_tokens),
        }

    def _get_warnings(self, system: int, doc: int, history: int, tools: int) -> list[str]:
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
        return warnings

    def trim_history(self, messages: list[dict], target_reduction: int = 0) -> list[dict]:
        """Trim history messages to fit within budget.

        Strategy: Remove oldest messages first, keeping system prompt and most recent exchanges.
        """
        if not messages:
            return messages

        # Separate system messages from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        # Calculate current history tokens
        current_tokens = estimate_messages_tokens(conv_msgs)

        if target_reduction <= 0 and current_tokens <= self.history_max:
            return messages

        # Remove oldest messages until we fit
        while conv_msgs and current_tokens > self.history_max:
            removed = conv_msgs.pop(0)
            current_tokens -= estimate_message_tokens(removed)

        return system_msgs + conv_msgs

    def summarize_if_needed(self, messages: list[dict], summarize_fn=None) -> list[dict]:
        """Summarize old messages if over budget.

        Args:
            messages: List of chat messages
            summarize_fn: Function to generate summary (text) -> text

        Returns:
            Optimized message list
        """
        budget = self.analyze_messages(messages)

        if not budget["over_budget"]:
            return messages

        # If no summarize function, just trim
        if summarize_fn is None:
            reduction_needed = budget["total_used"] - self.available_tokens
            return self.trim_history(messages, reduction_needed)

        # Separate system from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        if len(conv_msgs) <= 4:
            return messages

        # Split: old messages to summarize, recent to keep
        split_point = len(conv_msgs) - 6
        old_msgs = conv_msgs[:split_point]
        recent_msgs = conv_msgs[split_point:]

        # Generate summary of old messages
        old_text = "\n".join(
            f"{m.get('role', 'unknown')}: {m.get('content', '')[:200]}"
            for m in old_msgs
            if m.get("content")
        )

        try:
            summary = summarize_fn(old_text)
            summary_msg = {"role": "system", "content": f"Resumo da conversa anterior:\n{summary}"}
            return system_msgs + [summary_msg] + recent_msgs
        except Exception:
            # Fallback to trimming if summarization fails
            return self.trim_history(messages)

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
        }


def get_budget(num_ctx: int | None = None) -> ContextBudget:
    """Get a ContextBudget instance."""
    return ContextBudget(num_ctx)
