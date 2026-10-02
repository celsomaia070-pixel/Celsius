#!/usr/bin/env python
"""Run the golden-set test in a completely fresh process."""

import subprocess
import sys

# Run the test in a completely fresh process
code = '''
import importlib
import ai.tool_retrieval as tr
importlib.reload(tr)
from ai.tools import REGISTRO_FERRAMENTAS

prompt = "quais documentos eu tenho?"
embeddings = tr._tool_embeddings(REGISTRO_FERRAMENTAS)
print(f"Embeddings keys: {list(embeddings.keys())[:5]}")
scores = tr.score_tools(prompt)
print(f"Scores: {sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]}")
print(f"is_operational: {tr.is_operational('quais documentos eu tenho?', scores)}")
print(f"top_tools: {tr.top_tools(scores)}")

# Now test _filtrar_ferramentas
import ai.react as ai_react_mod
importlib.reload(ai_react_mod)
ferramentas = ai_react_mod._filtrar_ferramentas("quais documentos eu tenho?")
print(f"_filtrar_ferramentas: {[f.nome for f in ferramentas]}")

# Run harness
import evals.harness as harness_mod
importlib.reload(harness_mod)
manual = harness_mod.run("atual")
if manual.cases:
    m0 = manual.cases[0]
    print(f"case0: id={m0.id}, offered={m0.offered_tools}, expected={m0.expected_tools}")
'''

result = subprocess.run([
    sys.executable, "-c", code
], capture_output=True, text=True, timeout=300)

print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("Return code:", result.returncode)