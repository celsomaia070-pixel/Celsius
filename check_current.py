import sys
import importlib
import tests.test_golden_set
importlib.reload(tests.test_golden_set)
import evals.harness
importlib.reload(evals.harness)

from tests.test_golden_set import *
from evals import harness

current = harness.run('atual')
print('zero_tool_rate:', current.metrics['zero_tool_rate_operational'])
print('mode_accuracy:', current.metrics['mode_accuracy'])
print('tool_recall:', current.metrics['tool_recall'])