import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent

def control():
    return json.loads((BASE / "worker-state.json").read_text())

def mutate_if_editing():
    state = control()
    if state["phase"] == "editing":
        path = BASE / "policy.py"
        current = path.read_text()
        path.write_text(current.replace("20", "21").replace("22", "20") if "20" in current else current.replace("21", "22"))
        state["writes"] += 1
        (BASE / "worker-state.json").write_text(json.dumps(state))

if __name__ == "__main__":
    if sys.argv[1:] == ["handoff"]:
        state = control()
        state["phase"] = "stopped"
        (BASE / "worker-state.json").write_text(json.dumps(state))
        print("Worker stopped edits to policy.py and render.py until explicit resume")
    elif sys.argv[1:] == ["status"]:
        print(json.dumps(control()))
    else:
        raise SystemExit("usage: worker.py handoff|status")
