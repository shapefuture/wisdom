#!/usr/bin/env python3
"""Authoritative local delivery tracker with atomic CAS claims and durable memory."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / ".delivery/tracker.json"
LOCK = ROOT / ".delivery/runtime/tracker.lock"

def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit("Use snapshot, recall, remember, comments, comment, claim, update, or task.")
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw = FILE.read_bytes()
        state = json.loads(raw)
        revision = hashlib.sha256(raw).hexdigest()
        command = args[0]
        by_id = {x["id"]: x for x in state["items"]}
        result = None
        write = False
        if command == "snapshot":
            ready = [x["id"] for x in state["items"] if x["status"] in {"open","in_progress"} and not x.get("blocked") and all(by_id[d["depends_on_id"]]["status"] == "closed" for d in x.get("dependencies",[]) if d.get("type","blocks")=="blocks")]
            result = {"revision": revision, "items": state["items"], "ready_ids": ready}
        elif command == "recall":
            print(state.get("memories", {}).get(args[1], ""))
            return
        elif command == "remember":
            state.setdefault("memories", {})[args[1]] = args[2]
            write = True
            result = {"remembered": args[1]}
        elif command in {"comments","comment","task","claim","update"}:
            row = by_id[args[1]]
            if command == "comments":
                result = row.get("comments",[])
            elif command == "comment":
                row.setdefault("comments",[]).append({"text":args[2]})
                write = True
                result = {"commented":row["id"]}
            elif command == "task":
                result = row
            elif command == "claim":
                if len(args)<4 or args[3]!=revision:
                    raise ValueError("Stale claim: supply current snapshot revision.")
                if row["status"] != "open" or row.get("blocked"):
                    raise ValueError("Task is not claimable.")
                if any(by_id[d["depends_on_id"]]["status"]!="closed" for d in row.get("dependencies",[]) if d.get("type","blocks")=="blocks"):
                    raise ValueError("Blocking predecessor is unfinished.")
                row.update(status="in_progress", owner=args[2])
                write = True
                result = row
            else:
                patch = json.loads(args[2])
                if patch.get("status",row["status"]) not in {"open","in_progress","blocked","deferred","closed"}:
                    raise ValueError("Invalid state.")
                if "id" in patch and patch["id"]!=row["id"]:
                    raise ValueError("Identity is immutable.")
                row.update(patch)
                write = True
                result = row
        else:
            raise ValueError("Unknown operation.")
        if write:
            data = (json.dumps(state,ensure_ascii=False,indent=2)+"\n").encode()
            with tempfile.NamedTemporaryFile(dir=FILE.parent,delete=False) as out:
                out.write(data); out.flush(); os.fsync(out.fileno()); name=out.name
            os.replace(name,FILE)
        print(json.dumps(result,ensure_ascii=False))

if __name__ == "__main__":
    try:
        main()
    except (ValueError,KeyError,IndexError,OSError,json.JSONDecodeError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(1)

