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