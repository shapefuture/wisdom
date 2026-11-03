"""Fail-closed serving permissions over canonical record and source ancestry."""
from __future__ import annotations
from datetime import datetime,timezone
from .errors import NotFound

REF_KEYS={"source_id","source_ids","span_ids","claim_ids","theory_id","mechanism_ids",
          "evidence_ids","prediction_id","hypothesis_id","idea_id","experiment_id",
          "problem_id","parent_id","source_refs"}
RELATIONS={"DEPENDS_ON","QUOTES","INTERPRETS","INSPIRED_BY","BACKED_BY","SUPPORTS","ATTRIBUTES_TO",
           "TESTS","PREDICTS","OBSERVED_AS","STRUCTURALLY_MATCHES","USES_EVIDENCE","EVIDENCE_FOR","DERIVED_FROM","BASED_ON"}

def references(data):
    result=[]
    if isinstance(data,dict):
        if data.get("analysis_kind")=="evidence_analysis_plan" and not data.get("source_id"):
            key=data.get("analysis_key","")
            if isinstance(key,str) and key.startswith("evidence-analysis:"):result.append(key.split(":")[1])
        for key,value in data.items():
            if key in REF_KEYS or key.endswith("_id") or key.endswith("_ids"):
                result.extend(value if isinstance(value,list) else [value])
            if isinstance(value,(dict,list)):result.extend(references(value))
    elif isinstance(data,list):
        for value in data:
            if isinstance(value,(dict,list)):result.extend(references(value))
    return [x for x in result if isinstance(x,str) and x]

def ancestry(store,record,seen=None,stack=None):
    seen=set() if seen is None else seen
    stack=set() if stack is None else stack
    if record['id'] in stack:raise NotFound('Cyclic or unresolved provenance dependency.')
    if record["id"] in seen:return []
    seen.add(record["id"])
    stack.add(record['id'])
    found=[record]
    if record["kind"]=="source":
        stack.remove(record['id'])
        return found
    refs=references(record["data"])
    if record['kind']!='span':
        for edge in store.edges(record["id"]):
            if edge["source_id"]==record["id"] and edge["relation"].upper() in RELATIONS:
                refs.append(edge["target_id"])
    for rid in dict.fromkeys(refs):
        # Missing declared lineage is an access failure, never absence of restrictions.
        found.extend(ancestry(store,store.get(rid),seen,stack))
    stack.remove(record['id'])
    return found

def sources_for(store,record,seen=None):
    return [r for r in ancestry(store,record,seen) if r["kind"]=="source"]

def purpose_flag(purpose):
    p=purpose.casefold().replace("-","_")
    if p in {"model","model_processing"}:return "allow_model"
    if p in {"export","publish","share","send","download","upload"}:return "allow_export"
    if p in {"external","external_research"}:return "allow_external_research"
    return None

def allowed(store,record,*,purpose="read",include_private=True):
    purpose=purpose.casefold().replace('-','_')
    try:records=ancestry(store,record)
    except (NotFound,KeyError,TypeError):return False
    if record['kind'] in {'span','claim','utterance','argument','interpretation','viewpoint'} and not any(r['kind']=='source' for r in records):return False
    flag=purpose_flag(purpose)
    for subject in records:
        data=subject["data"];status=str(data.get("status","")).upper()
        security=str(data.get("security_status","")).upper()
        if (data.get("deleted") or data.get("poisoned") or data.get("poisoning_suspected")
            or data.get("quarantined") or data.get("injection_suspected")
            or status in {"BLOCKED","EXPIRED","DELETED","QUARANTINE","QUARANTINED","REFUSE"}
            or security in {"POISONED","QUARANTINED","DENIED","EXPIRED"}):return False
        rights=data.get("rights")
        is_source=subject["kind"]=="source"
        if rights is not None and not isinstance(rights,dict):return False
        rights=rights or {}
        if is_source and rights.get("allowed") is not True:return False
        if "allowed" in rights and rights["allowed"] is not True:return False
        if not include_private and rights.get("private"):return False
        if flag:
            # Source grants are affirmative; derived records may only narrow them.
            if is_source and rights.get(flag) is not True:return False
            if flag in rights and rights[flag] is not True:return False
            if flag=="allow_model" and data.get("allow_model") is False:return False
        if purpose in {"external","external_research"} and rights.get("private"):return False
        expiry=rights.get("expires_at") or data.get("expires_at")
        if expiry:
            try:
                expires=datetime.fromisoformat(expiry.replace("Z","+00:00"))
                if expires.tzinfo is None or expires<=datetime.now(timezone.utc):return False
            except (ValueError,TypeError,AttributeError):return False
    return True

