"""Test-only authoritative tracker stand-in. Never a production/export fallback."""
import json
from pathlib import Path
import sys

project, operation, *arguments = sys.argv[1:]
path = Path(project) / ".delivery/runtime/test-tracker.json"
state = json.loads(path.read_text())
if operation == "snapshot":
    print(json.dumps(state["snapshot"]))
elif operation == "recall":
    print(state["memories"][arguments[0]])
elif operation == "comments":
    print(json.dumps(state["comments"].get(arguments[0], [])))
elif operation == "remember":
    state["memories"][arguments[0]] = arguments[1]
    path.write_text(json.dumps(state))
    print("stored")
elif operation == "comment":
    state["comments"].setdefault(arguments[0], []).append({"text": arguments[1]})
    path.write_text(json.dumps(state))
    print("stored")
else:
    raise SystemExit("unsupported test fixture operation")

