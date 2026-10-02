#!/usr/bin/env python
"""Run golden-set tests in a completely fresh subprocess."""

import subprocess
import sys

code = '''
import sys
import importlib

# Fresh imports
import evals.harness as harness_mod
importlib.reload(harness_mod)

# Run all three comparison modes
runs = [
    harness_mod.run("atual", select=harness_mod.select_current, mode=harness_mod._mode_for),
    harness_mod.run("lexical_only", select=harness_mod.select_lexical_only, mode=harness_mod._mode_lexical_only),
    harness_mod.run("semantic_only", select=harness_mod.select_semantic_only, mode=harness_mod._mode_for),
]

print("=== METRICS ===")
for r in runs:
    m = r.metrics
    print(f'{r.label}: tool_recall={m["tool_recall"]:.4f}, zero_tool_rate={m["zero_tool_rate_operational"]:.4f}, mode_accuracy={m["mode_accuracy"]:.4f}')

# Now check the assertions
current = runs[0]
m = current.metrics

print()
print("=== ASSERTIONS ===")
print(f'tool_recall >= 0.90: {m[\"tool_recall\"]:.4f} >= 0.90 = {m[\"tool_recall\"] >= 0.90}')
print(f'zero_tool_rate <= 0.05: {m[\"zero_tool_rate_operational\"]:.4f} <= 0.05 = {m[\"zero_tool_rate_operational\"] <= 0.05}')
print(f'mode_accuracy >= 0.85: {m[\"mode_accuracy\"]:.4f} >= 0.85 = {m[\"mode_accuracy\"] >= 0.85}')

# Check paraphrases
from evals.cases import by_category
paraphrases = {c.id for c in harness_mod.CASES if c.category == "E"}
hits = [c for c in runs[0].cases if c.id in paraphrases and c.recall_hit]
print(f"paraphrase hits: {len(hits)}/{len(paraphrases)} = {len(hits)/len(paraphrases):.2f}")

# Check semantic gains
lexical = runs[1]
lexical_by_id = {c.id: set(c.offered_tools) for c in lexical.cases}
real_gains = []
for case in runs[0].cases:
    extra = set(case.offered_tools) - {c.id: set(c.offered_tools) for c in lexical.cases}[case.id]
    real_gains.extend(extra & set(case.expected_tools))
print(f"real_gains: {len(real_gains)}")

# Overall pass
all_pass = (
    m["tool_recall"] >= 0.90 and
    m["zero_tool_rate_operational"] <= 0.05 and
    m["mode_accuracy"] >= 0.85 and
    len(real_gains) > 0 and
    (len([c for c in runs[0].cases if c.id in {c.id for c in evals.cases.CASES if c.category == "E"} and c.recall_hit]) / len({c.id for c in evals.cases.CASES if c.category == "E"})) >= 0.7
)
print(f"ALL PASS: {all_pass}")
sys.exit(0 if all_pass else 1)
'''

result = subprocess.run([
    sys.executable, "-c", code
], capture_output=True, text=True, timeout=300)

print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("Return code:", result.returncode)