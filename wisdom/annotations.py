"""Human-reviewed dialogue, argument, interpretation and disagreement annotations."""
from .access import allowed
from .errors import ValidationError,PermissionDenied

class AnnotationService:
    def __init__(self,store):self.store=store

    def record(self,payload):
        kind=payload.get("kind")
        if kind not in {"utterance","argument","interpretation","viewpoint","contradiction"}:
            raise ValidationError("Unsupported annotation kind.")
        reviewer=payload.get("reviewer")
        if not isinstance(reviewer,str) or not reviewer.strip():
            raise ValidationError("Annotations require the human reviewer's identity.")
        data=payload.get("data")
        if not isinstance(data,dict):raise ValidationError("Annotation data must be an object.")
        data=dict(data)
        if kind=="contradiction":
            ids=data.get("claim_ids",[])
            if not isinstance(ids,list) or len(set(ids))!=2:
                raise ValidationError("A disagreement requires two distinct anchored claims.")
            if data.get("conflict_type") not in {"empirical","semantic","normative","design","philosophical_aporia"}:
                raise ValidationError("Choose a conflict type; normative disputes are not fact-checked away.")
            claims=[self.store.get(rid) for rid in ids]
            if any(r["kind"]!="claim" or not allowed(self.store,r) for r in claims):
                raise PermissionDenied("Disagreement must reference available source claims.")
            if not isinstance(data.get("reason"),str) or not data["reason"].strip():
                raise ValidationError("Describe the precise proposition in conflict.")
            record=self.store.put("assessment",{**data,"assessment_kind":"contradiction","reviewer":reviewer,
                                  "epistemic_type":"INTERPRETATION","resolution":"unresolved"},
                                  idempotency_key=payload.get("idempotency_key"),event_type="CONTRADICTION_RECORDED")
            if not any(e["source_id"]==ids[0] and e["target_id"]==ids[1] and e["relation"]=="CONTRADICTS" for e in self.store.edges(ids[0])):
                self.store.link(ids[0],ids[1],"CONTRADICTS",polarity="negative",
                                data={"assessment_id":record["id"],"conflict_type":data["conflict_type"]})
            return record
        source_id=data.get("source_id")
        source=self.store.get(source_id)
        if source["kind"]!="source" or not allowed(self.store,source):
            raise PermissionDenied("Annotation source is restricted or unavailable.")
        span_ids=data.get("span_ids",[])
        if not isinstance(span_ids,list) or not span_ids:
            raise ValidationError("Annotations require exact source spans.")
        spans=[self.store.get(rid) for rid in span_ids]
        if len(set(span_ids))!=len(span_ids):raise ValidationError('Annotation spans must be distinct.')
        if any(s["kind"]!="span" or s["data"].get("source_id")!=source_id for s in spans):
            raise ValidationError("Every annotation anchor must belong to its source.")
        spans.sort(key=lambda s:s['data']['start_char'])
        for span in spans:
            d=span["data"];original=source["data"].get("original_text",source["data"].get("text",""))
            if original[d["start_char"]:d["end_char"]]!=d["text"]:
                raise ValidationError("A cited span failed exact-source verification.")
        if kind=="utterance":
            if not isinstance(data.get("turn"),int) or isinstance(data.get("turn"),bool) or data["turn"]<0:
                raise ValidationError("Utterance turn is a nonnegative integer.")
            if data.get("speech_act") not in {"assertion","question","objection","clarification","retraction","example","metaphor","unknown"}:
                raise ValidationError("Unknown speech act.")
            data["text"]="\n".join(s["data"]["text"] for s in spans)
            data["speaker_uncertain"]=data.get("speaker_uncertain",True) is not False
            data["epistemic_type"]="SOURCE_REPORT"
        elif kind=="argument":
            for field in ("claim","grounds","warrant","backing","qualifier","rebuttal"):
                if not isinstance(data.get(field),str):
                    raise ValidationError("Argument annotations need claim/grounds/warrant/backing/qualifier/rebuttal; use explicit unresolved text.")
            data["epistemic_type"]="INTERPRETATION"
        elif kind=="interpretation":
            if not isinstance(data.get("reading"),str) or not data["reading"].strip():
                raise ValidationError("An interpretation needs a reading.")
            data["epistemic_type"]="INTERPRETATION"
            data.setdefault("evidence_for",[]);data.setdefault("evidence_against",[])
            data.setdefault("lens","human_proposed_reading")
        else:
            if data.get("stance") not in {"endorsement","dissent","alternative","unresolved"}:
                raise ValidationError("Viewpoint stance must preserve endorsement, dissent, alternatives or unresolved position.")
            if not data.get("position") or not data.get("context"):
                raise ValidationError("A viewpoint needs its expressed position and context.")
            for rid in data.get("claim_ids",[]):
                claim=self.store.get(rid)
                if claim["kind"]!="claim" or not allowed(self.store,claim):
                    raise ValidationError("Viewpoint claims must be available anchored records.")
            data["epistemic_type"]="INTERPRETATION"
        data.update(reviewer=reviewer,review_status="human_annotated")
        record=self.store.put(kind,data,immutable=kind=="utterance",idempotency_key=payload.get("idempotency_key"),
                              event_type="HUMAN_ANNOTATION_RECORDED")
        existing={(e["target_id"],e["relation"]) for e in self.store.edges(record["id"]) if e["source_id"]==record["id"]}
        relation='QUOTES' if kind=='utterance' else 'INTERPRETS'
        for span in spans:
            if (span["id"],relation) not in existing:
                self.store.link(record["id"],span["id"],relation)
        return record

