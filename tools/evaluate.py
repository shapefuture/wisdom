#!/usr/bin/env python3
"""Reproducible synthetic mechanics evaluation, never empirical product superiority."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from wisdom.composition import Application

def main():
    app=Application()
    try:
        text="The intervention may help under stable feedback. It does not always work."
        src=app.ingest.ingest({"title":"Synthetic holdout mechanics fixture","text":text,"source_family":"synthetic-v1",
                              "rights":{"allowed":True,"license":"test-fixture","private":False,"allow_export":True}})
        out=app.evidence.analyze(src["id"])
        spans=app.ingest.spans(src["id"])
        exact=all(text[r["data"]["start_char"]:r["data"]["end_char"]]==r["data"]["text"] for r in spans)
        negation=any("not always" in r["data"]["text"] for r in out["claims"])
        unknown=app.invention.problem({"title":"Unrelated target","description":"A different problem with no mechanism",
                  "desired_state":"improve","maintaining_force":"unknown","actors":[],"constraints":[],"failed_attempts":[],"domain":"unknown","stakes":"low"})
        forged=app.invention.forge(unknown["id"])
        no_forced=not forged["ideas"] and bool(forged["missing_evidence"])
        results={"dataset":"synthetic-mechanics-v1","exact_anchor_check":exact,"negation_retained":negation,
                 "no_forced_match":no_forced,"ledger_integrity":app.store.verify_ledger()["valid"],
                 "A0_A6_human_comparison":"not run","real_world_effect":"unmeasured","human_capability":"unmeasured"}
        print(json.dumps(results,indent=2))
        return not all([exact,negation,no_forced,results["ledger_integrity"]])
    finally:app.close()
if __name__=="__main__":raise SystemExit(main())

