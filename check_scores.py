import importlib
import ai.tool_retrieval as tr
importlib.reload(tr)

prompt = "quais documentos eu tenho?"
scores = tr.score_tools(prompt)
print("Scores top 10:")
for k, v in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]:
    print(f"  {k}: {v:.4f}")
print()
op = tr.is_operational(prompt, tr.score_tools(prompt))
print(f"is_operational: {op}")
print(f"top_tools: {tr.top_tools(tr.score_tools(prompt))}")