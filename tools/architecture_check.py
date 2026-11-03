#!/usr/bin/env python3
"""Executable minimal architecture gates; no numerical conformance score."""
import ast
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wisdom.ports import StorePort
from wisdom.store import Store

def main():
    errors=[]
    domain={"governance","evidence","theory","invention","learning","memory","retrieval","workflows","watchdog"}
    for name in domain:
        path=ROOT/"wisdom"/(name+".py")
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.level==1 and node.module in {"store","api","composition","cli"}:
                errors.append(f"{name} depends on concrete composition/adapter {node.module}")
            if isinstance(node,ast.Import) and any(n.name.split(".")[0] in {"sqlite3","subprocess"} for n in node.names):
                errors.append(f"{name} imports a forbidden infrastructure/execution module")
    constitution=json.loads((ROOT/"architecture/constitution.json").read_text())
    if len(constitution["invariants"])<5:errors.append("Constitution is incomplete")
    slots=json.loads((ROOT/"architecture/slots.json").read_text())
    if slots["composition_root"]!="wisdom/composition.py":errors.append("Composition root missing")
    for method in ("put","get","list","history","link","edges","search","append_event","events","verify_ledger","purge_source","close"):
        if not callable(getattr(Store,method,None)):errors.append("Store slot missing "+method)
    mission=json.loads((ROOT/".delivery/mission.json").read_text())
    mapped={r["id"] for r in mission["requirements"]}
    if any(f"SPEC-{n:02d}" not in mapped for n in range(1,23)):errors.append("Blueprint scope coverage lost")
    print(json.dumps({"passed":not errors,"checks":["domain adapter isolation","store port completeness","constitution","logical slots","22-section scope coverage"],"errors":errors},indent=2))
    return bool(errors)
if __name__=="__main__":raise SystemExit(main())

