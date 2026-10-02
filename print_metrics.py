from evals import harness

r = harness.run("atual")
m = r.metrics

print("=== Métricas com encoder ativo ===")
print(f"tool_recall: {m['tool_recall']:.4f}")
print(f"tool_precision: {m['tool_precision']:.4f}")
print(f"mode_accuracy: {m['mode_accuracy']:.4f}")
print(f"zero_tool_rate: {m['zero_tool_rate_operational']:.4f}")
print(f"false_tool_rate: {m['false_tool_rate_on_general']:.4f}")
print(f"avg_tools: {m['tools_offered_avg']:.2f}")
print(f"recall@1: {m['recall_at_1']:.4f}")
print(f"recall@3: {m['recall_at_3']:.4f}")

print("\n=== Por categoria ===")
cats = r.per_category()
for cat in sorted(cats):
    b = cats[cat]
    recall = b["recall_hits"] / b["total"] if b["total"] else 0.0
    mode = f"{b['mode_ok']}/{b['mode_total']}" if b["mode_total"] else "-"
    print(f"  {cat}: recall {recall:.2f} ({int(b['recall_hits'])}/{int(b['total'])})  mode {mode}")

print("\n=== Comparativo (lexical vs encoder ativo) ===")
print(f"{'Métrica':<25} {'Lexical':>10} {'Encoder':>10} {'Variação':>12}")
print("-" * 57)
print(
    f"{'tool_recall':<25} {0.4135:>10.4f} {m['tool_recall']:>10.4f} {m['tool_recall'] - 0.4135:>+11.4f}"
)
print(
    f"{'tool_precision':<25} {0.5699:>10.4f} {m['tool_precision']:>10.4f} {m['tool_precision'] - 0.5699:>+11.4f}"
)
print(
    f"{'mode_accuracy':<25} {0.6842:>10.4f} {m['mode_accuracy']:>10.4f} {m['mode_accuracy'] - 0.6842:>+11.4f}"
)
print(
    f"{'zero_tool_rate':<25} {0.4615:>10.4f} {m['zero_tool_rate_operational']:>10.4f} {m['zero_tool_rate_operational'] - 0.4615:>+11.4f}"
)
print(
    f"{'false_tool_rate':<25} {0.0909:>10.4f} {m['false_tool_rate_on_general']:>10.4f} {m['false_tool_rate_on_general'] - 0.0909:>+11.4f}"
)
print(
    f"{'avg_tools':<25} {0.89:>10.2f} {m['tools_offered_avg']:>10.2f} {m['tools_offered_avg'] - 0.89:>+11.2f}"
)
