"""Read-only assurance inspection, separated from generation and promotion."""
import hashlib
from .access import allowed, sources_for
from .errors import NotFound

class Watchdog:
    def __init__(self,store):self.store=store
    def audit(self):
        ledger=self.store.verify_ledger()
        findings=[]
        records=self.store.list()
        by_id={r["id"]:r for r in records}
        for r in records:
            d=r["data"]
            if r["kind"]=="span":
                try:
                    src=self.store.get(d["source_id"])["data"]
                    original=src.get("text",src.get("original_text",""))
                    start,end=d.get("start_char"),d.get("end_char")
                    if not isinstance(start,int) or not isinstance(end,int) or original[start:end]!=d.get("text"):
                        findings.append({"id":r["id"],"severity":"high","code":"SPAN_MISMATCH","reason":"Span does not match the immutable original."})
                except (NotFound,KeyError):
                    findings.append({"id":r["id"],"severity":"high","code":"MISSING_SOURCE","reason":"Source anchor missing."})
            if r["kind"]=="claim" and not d.get("span_ids"):
                findings.append({"id":r["id"],"severity":"high","code":"UNANCHORED_CLAIM","reason":"Attributed claim has no exact span."})
            if r["kind"] in {"theory","mechanism","idea"} and d.get("epistemic_type") in {"SOURCE_REPORT","TESTED_FINDING"} and not d.get("outcome_ids"):
                findings.append({"id":r["id"],"severity":"high","code":"TYPE_LAUNDERING","reason":"Generated item claims a source/test status without outcome evidence."})
            if r["kind"]=="skill" and d.get("status") in {"authorized","AUTHORIZED_SKILL"} and not (d.get("authorization") or d.get("authorized_by")):
                findings.append({"id":r["id"],"severity":"high","code":"AUTHORITY_GAP","reason":"Skill lacks a separate human authorization record."})
        if not ledger.get("valid"):
            findings.append({"severity":"critical","code":"LEDGER_INTEGRITY","reason":"Event chain verification failed."})
        return {"ledger":ledger,"findings":findings,"critical_count":sum(f["severity"] in {"high","critical"} for f in findings),
                "records_checked":len(records),"empirical_validation":"pending independent corpus and human measurements",
                "external_actions_enabled":False}

