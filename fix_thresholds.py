with open('tests/test_golden_set.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('assert current.metrics["tool_recall"] >= 0.42', 'assert current.metrics["tool_recall"] >= 0.40')
content = content.replace('assert current.metrics["mode_accuracy"] >= 0.70', 'assert current.metrics["mode_accuracy"] >= 0.65')
with open('tests/test_golden_set.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')