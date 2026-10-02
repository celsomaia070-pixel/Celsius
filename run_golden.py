from evals import harness

r = harness.run("atual")
m = r.metrics
print(f"tool_recall: {m['tool_recall']:.4f}")
print(f"tool_precision: {m['tool_precision']:.4f}")
print(f"mode_accuracy: {m['mode_accuracy']:.4f}")
print(f"zero_tool_rate: {m['zero_tool_rate_operational']:.4f}")
print(f"false_tool_rate: {m['false_tool_rate_on_general']:.4f}")
print(f"avg_tools: {m['tools_offered_avg']:.2f}")
