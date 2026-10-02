import sys

sys.path.insert(0, "E:\\PythonProjectCELSIUS")

for mod_name in list(sys.modules.keys()):
    if "sentence_transformers" in mod_name:
        del sys.modules[mod_name]

import importlib

import ai.react
import ai.tool_retrieval
import core.agent_modes
import core.embeddings
import core.settings
import evals.harness

importlib.reload(evals.harness)
importlib.reload(ai.tool_retrieval)
importlib.reload(ai.react)
importlib.reload(core.agent_modes)
importlib.reload(core.settings)
importlib.reload(core.embeddings)
core.embeddings.clear_sentence_transformer_cache()

import ai.tool_retrieval as tr2

tr2._embeddings.clear()
tr2._embeddings_model = None
tr2._model_loaded = False

import ai.react as ai_react2

if hasattr(ai_react2, "_filtrar_ferramentas_cache"):
    ai_react2._filtrar_ferramentas_cache.clear()

import ai.tool_retrieval as tr
import evals.harness as hm

r = hm.run("atual")

for case in r.cases:
    scores = tr.score_tools(case.prompt)
    top = tr.top_tools(scores)
    expected = sorted(case.expected_tools) if case.expected_tools else "NONE"
    offered = sorted(case.offered_tools) if case.offered_tools else "NONE"
    hits = sorted(case.hits) if case.hits else "NONE"
    top8 = [(n, f"{s:.4f}") for n, s in top[:8]]
    print(f'{case.id} [{case.category}] "{case.prompt[:60]}"')
    print(f"  expected: {expected}")
    print(f"  offered:  {offered} ({len(case.offered_tools)})")
    print(f"  hits:     {hits}")
    print(f"  top scores: {top8}")
    print()
