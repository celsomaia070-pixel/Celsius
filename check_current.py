import importlib

import evals.harness

importlib.reload(evals.harness)

from evals import harness

current = harness.run("atual")
print("zero_tool_rate:", current.metrics["zero_tool_rate_operational"])
print("mode_accuracy:", current.metrics["mode_accuracy"])
print("tool_recall:", current.metrics["tool_recall"])
