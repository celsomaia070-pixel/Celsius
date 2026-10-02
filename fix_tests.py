with open('tests/test_golden_set.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix function signatures
content = content.replace('def test_tool_recall_does_not_regress(_current()):', 'def test_tool_recall_does_not_regress():')
content = content.replace('def test_zero_tool_rate_does_not_regress(_current()):', 'def test_zero_tool_rate_does_not_regress():')
content = content.replace('def test_mode_accuracy_does_not_regress(_current()):', 'def test_mode_accuracy_does_not_regress():')
content = content.replace('def test_semantic_layer_is_not_silently_inert(_current()):', 'def test_semantic_layer_is_not_silently_inert():')
content = content.replace('def test_paraphrases_are_not_solved_by_keywords(_current()):', 'def test_paraphrases_are_not_solved_by_keywords():')
content = content.replace('def test_baseline_is_recorded_with_its_measurement_path(_lexical()):', 'def test_baseline_is_recorded_with_its_measurement_path():')

# Fix references to current. and lexical.
content = content.replace('current.metrics', '_current().metrics')
content = content.replace('current.cases', '_current().cases')
content = content.replace('lexical.cases', '_lexical().cases')
content = content.replace('lexical_by_id = {c.id: set(c.offered_tools) for c in lexical.cases}', 'lexical_by_id = {c.id: set(c.offered_tools) for c in _lexical().cases}')
content = content.replace('lexical_only = harness.run("lexical_probe", select=harness.select_lexical_only)', 'lexical_only = _lexical()')

with open('tests/test_golden_set.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')