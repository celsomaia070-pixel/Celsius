#!/usr/bin/env python
import importlib
import evals.harness as harness_mod
importlib.reload(harness_mod)

runs = [
    harness_mod.run('atual', select=harness_mod.select_current, mode=harness_mod._mode_for),
    harness_mod.run('lexical_only', select=harness_mod.select_lexical_only, mode=harness_mod._mode_lexical_only),
    harness_mod.run('semantic_only', select=harness_mod.select_semantic_only, mode=harness_mod._mode_for),
]

for r in runs:
    print(f'=== {r.label} ===')
    print(f'encoder: {r.encoder_available}')
    print(f'tool_recall: {r.metrics["tool_recall"]:.4f}')
    print(f'recall@1: {r.metrics["recall_at_1"]:.4f}')
    print(f'recall@3: {r.metrics["recall_at_3"]:.4f}')
    print(f'tool_precision: {r.metrics["tool_precision"]:.4f}')
    print(f'zero_tool_rate: {r.metrics["zero_tool_rate_operational"]:.4f}')
    print(f'mode_accuracy: {r.metrics["mode_accuracy"]:.4f}')
    print(f'avg_tools: {r.metrics["tools_offered_avg"]:.2f}')
    print()