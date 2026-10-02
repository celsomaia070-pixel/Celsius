with open('tests/test_golden_set.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix all function signatures
import re

# Replace all function signatures that have (_current()) or (_lexical())
content = re.sub(r'def test_(\w+)\(_current\(\)\):', r'def test_\1():', content)
content = re.sub(r'def test_(\w+)\(_lexical\(\)\):', r'def test_\1():', content)

# Fix references to current. and lexical.
content = content.replace('current.metrics', '_current().metrics')
content = content.replace('current.cases', '_current().cases')
content = content.replace('lexical.cases', '_lexical().cases')
content = content.replace('lexical_by_id = {c.id: set(c.offered_tools) for c in lexical.cases}', 'lexical_by_id = {c.id: set(c.offered_tools) for c in _lexical().cases}')
content = content.replace('lexical_only = harness.run("lexical_probe", select=harness.select_lexical_only)', 'lexical_only = _lexical()')

with open('tests/test_golden_set.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')