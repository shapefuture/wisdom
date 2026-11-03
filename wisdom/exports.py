"""Rights-filtered portable exports. Source reports and hypotheses remain typed."""
import json
from datetime import datetime,timezone
from urllib.parse import urlparse
from .access import allowed

def export_bundle(store):
    records=[r for r in store.list() if r["kind"]!="job" and allowed(store,r,purpose="export")]
    ids={r["id"] for r in records}
    edges=[e for e in store.edges() if e["source_id"] in ids and e["target_id"] in ids]
    return {"schema_version":"1.0.0","exported_at":datetime.now(timezone.utc).isoformat(),
            "offset_unit":"unicode_codepoints","records":records,"edges":edges,
            "excluded_records":len(store.list())-len(records),
            "notice":"Source attribution is not empirical truth; generated ideas remain hypotheses. Rights restrictions apply to every derivative."}

def markdown(bundle):
    chunks=["# Wisdom Foundry export","",bundle["notice"],""]
    for r in bundle["records"]:
        d=r["data"]
        chunks.extend(["## "+str(d.get("title",d.get("question",r["kind"]))).replace("\n"," "),
                       "",f"ID: {r['id']} · Kind: {r['kind']} · Version: {r['version']}",
                       "", "Epistemic type: "+str(d.get("epistemic_type","unassessed")),""])
        if d.get("uri") and urlparse(str(d["uri"])).scheme in {"http","https"}:
            chunks.extend(["Original: "+str(d["uri"]),""])
        chunks.extend(["```json",json.dumps(d,ensure_ascii=False,indent=2),"```",""])
    return "\n".join(chunks)

def argdown(bundle):
    result=["# Source-linked argument export","","// Generated interpretations are proposals; claims are attributed, not proven.",""]
    for r in bundle["records"]:
        if r["kind"] in {"claim","argument"}:
            text=str(r["data"].get("text",r["data"].get("claim",""))).replace("\n"," ").replace("[","(").replace("]",")")
            result.append("["+r["id"]+"]: "+text)
    return "\n".join(result)+"\n"

