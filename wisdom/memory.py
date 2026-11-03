"""Human-owned goals, TRACE reflection, and intentionally quiet prospective memory."""
from datetime import datetime, timezone
import math
from .errors import ValidationError, PermissionDenied, Conflict
from .access import allowed

def now():
    return datetime.now(timezone.utc).isoformat()

def date(value):
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
        if d.tzinfo is None:raise ValueError()
        return d
    except (ValueError,AttributeError,TypeError):
        raise ValidationError("Use a timezone-aware ISO 8601 date.") from None

class MemoryService:
    def __init__(self,store):self.store=store

    def goal(self,payload):
        if payload.get("human_approved") is not True:
            raise PermissionDenied("Goals and values require explicit human approval.")
        if not str(payload.get("title","")).strip():
            raise ValidationError("Goal title is required.")
        data={**payload,"owner":payload.get("owner","local-user"),"human_approved":True,"epistemic_type":"NORMATIVE_POSITION"}
        return self.store.put("goal",data,idempotency_key=payload.get("idempotency_key"),event_type="GOAL_RECORDED")

    def trace(self,payload):
        stage=payload.get("stage","").upper()
        if stage not in {"NOTICE","INTERPRET","VALUE","EXPLORE","ACT","LEARN"}:
            raise ValidationError("Choose a TRACE stage.")
        if not str(payload.get("reflection","")).strip():
            raise ValidationError("A reflection is required.")
        data={**payload,"stage":stage,"human_first":payload.get("human_first") is True,
              "measurement_status":"self_report","capability_claim":"No cognitive capability ranking or diagnosis."}
        return self.store.put("trace",data,idempotency_key=payload.get("idempotency_key"),event_type="TRACE_RECORDED")

    def trigger(self,payload):
        conditions=payload.get("conditions",payload.get("condition"))
        if isinstance(conditions,dict):conditions=[conditions]
        if not isinstance(conditions,list) or not conditions:
            raise ValidationError("Triggers need typed conditions: [{signal,operator,value}].")
        for condition in conditions:
            if not isinstance(condition,dict) or not isinstance(condition.get("signal"),str) or condition.get("operator","eq") not in {"eq","gte","lte","contains","changed"}:
                raise ValidationError("Invalid trigger condition.")
            if condition.get("operator") in {"gte","lte"} and (not isinstance(condition.get("value"),(int,float)) or isinstance(condition.get("value"),bool) or not math.isfinite(condition["value"])):
                raise ValidationError("Numeric trigger bounds must be finite.")
        expiry=payload.get("expires_at")
        if not expiry or date(expiry)<=datetime.now(timezone.utc):
            raise ValidationError("Triggers require a future expiry.")
        if payload.get("authority","advisory_only")!="advisory_only":
            raise PermissionDenied("Prospective triggers may prepare private suggestions only.")
        for rid in payload.get("linked_ids",[]):self.store.get(rid)
        return self.store.put("trigger",{**payload,"conditions":conditions,"authority":"advisory_only","status":"active","last_signal_hash":None},
                              idempotency_key=payload.get("idempotency_key"),event_type="TRIGGER_REGISTERED")

    def evaluate(self,signals,budget=3):
        import hashlib,json
        if not isinstance(signals,dict) or not isinstance(budget,int) or isinstance(budget,bool) or not 0<=budget<=50:
            raise ValidationError("Signals must be an object; attention budget is 0–50.")
        notifications=[];suppressed=[]
        for rec in self.store.list("trigger"):
            d=rec["data"]
            if d.get("status")!="active":continue
            if date(d["expires_at"])<=datetime.now(timezone.utc):
                self.store.put("trigger",{**d,"status":"expired"},record_id=rec["id"],expected_version=rec["version"],event_type="TRIGGER_EXPIRED")
                suppressed.append({"id":rec["id"],"reason":"expired"});continue
            if not allowed(self.store,rec):
                suppressed.append({"id":rec["id"],"reason":"linked evidence is restricted or expired"})
                continue
            relevant={c["signal"]:signals.get(c["signal"]) for c in d["conditions"]}
            digest=hashlib.sha256(json.dumps(relevant,sort_keys=True,allow_nan=False).encode()).hexdigest()
            matches=True
            for c in d["conditions"]:
                value=signals.get(c["signal"]);target=c.get("value");op=c.get("operator","eq")
                if c["signal"] not in signals:matches=False;break
                try:
                    matched={"eq":lambda:value==target,"gte":lambda:isinstance(value,(int,float)) and not isinstance(value,bool) and value>=target,
                             "lte":lambda:isinstance(value,(int,float)) and not isinstance(value,bool) and value<=target,
                             "contains":lambda:target in value,"changed":lambda:d.get("last_signal_hash") is not None and digest!=d["last_signal_hash"]}[op]()
                except (TypeError,KeyError):matched=False
                matches=matches and matched
            duplicate=d.get("last_notified_hash")==digest
            if matches and not duplicate and len(notifications)<budget:
                # CAS before returning: concurrent evaluations cannot both notify.
                try:
                    self.store.put("trigger",{**d,"last_signal_hash":digest,"last_notified_hash":digest,"last_fired_at":now()},
                                   record_id=rec["id"],expected_version=rec["version"],event_type="TRIGGER_FIRED")
                except Conflict:
                    suppressed.append({"id":rec["id"],"reason":"concurrent evaluation"});continue
                notifications.append({"id":rec["id"],"title":d.get("title","Revisit an option"),"suggestion":d.get("suggestion",d.get("action","Review linked evidence.")),
                                      "linked_ids":d.get("linked_ids",[]),"authority":"advisory_only"})
            else:
                if d.get("last_signal_hash")!=digest:
                    self.store.put("trigger",{**d,"last_signal_hash":digest},record_id=rec["id"],expected_version=rec["version"],event_type="TRIGGER_CHECKED")
                suppressed.append({"id":rec["id"],"reason":"duplicate" if duplicate else "attention budget" if matches else "conditions unmet"})
        return {"notifications":notifications,"suppressed":suppressed}

