"""Durable bounded workflow states and task-specific deterministic routing."""
import hashlib
import json
import os
from datetime import datetime, timezone
from .errors import ValidationError, Conflict, FoundryError

class WorkflowService:
    def __init__(self,store):
        self.store=store
        self.handlers={}

    def bind(self,kind,handler):
        self.handlers[kind]=handler

    def route(self,payload):
        objective=payload.get("objective","EXECUTE").upper()
        if objective not in {"EXECUTE","DISCOVER","RETHINK"}:raise ValidationError("Invalid objective loop.")
        stakes=payload.get("stakes","low")
        if stakes not in {"low","medium","high","critical"}:raise ValidationError("Invalid stakes.")
        if payload.get("emergency"):mode="CRISIS"
        elif stakes in {"high","critical"} or payload.get("wicked"):mode="DEEP"
        elif payload.get("stuck_type") or payload.get("failed_attempts"):mode="ENGINE"
        else:mode="DIRECT"
        budget=payload.get("budget",{})
        if not isinstance(budget,dict):raise ValidationError("Budget must be an object.")
        return {"objective":objective,"mode":mode,"stakes":stakes,
                "engines":["EVIDENCE"] if mode=="DIRECT" else ["EVIDENCE","THEORY","INVENTION"],
                "human_review_required":stakes in {"high","critical"} or payload.get("value_conflict") is True,
                "permitted_effects":["read","propose"],"budget":budget,
                "next_step":"Seek immediate qualified human help; this system does not handle emergencies." if mode=="CRISIS" else
                "Clarify human decision rights and missing evidence." if payload.get("value_conflict") else
                "Use the smallest evidence packet that could change the choice.",
                "autonomy":"advisory_only"}

    def run(self,kind,payload,key=None):
        if kind not in self.handlers:raise ValidationError("Unknown workflow operation.")
        if not isinstance(payload,dict):raise ValidationError("Workflow input must be an object.")
        key=key or payload.get("idempotency_key")
        fingerprint=hashlib.sha256(json.dumps([kind,payload],sort_keys=True,allow_nan=False).encode()).hexdigest()
        if key:
            matches=[r for r in self.store.list("job") if r["data"].get("idempotency_key")==key]
            if matches:
                if matches[0]["data"].get("fingerprint")!=fingerprint:raise Conflict("Idempotency key was used for a different job.")
                return matches[0]
        handler_payload={**payload,"idempotency_key":"workflow:"+fingerprint}
        job=self.store.put("job",{"operation":kind,"payload":handler_payload,"fingerprint":fingerprint,"idempotency_key":key,
                                 "status":"pending","attempts":0,"max_attempts":3,"effects":"advisory/local-only"},
                           idempotency_key=("job:"+key) if key else None,event_type="JOB_QUEUED")
        return self._execute(job)

    def _execute(self,job):
        d=job["data"]
        if d["attempts"]>=d["max_attempts"]:raise Conflict("Retry limit reached; create a new explicit job after review.")
        active=self.store.put("job",{**d,"status":"running","attempts":d["attempts"]+1,"worker_pid":os.getpid(),"started_at":datetime.now(timezone.utc).isoformat()},
                              record_id=job["id"],expected_version=job["version"],event_type="JOB_STARTED")
        try:
            result=self.handlers[d["operation"]](d["payload"])
            state={**active["data"],"status":"completed","result":result,"error":None}
        except Exception as exc:
            # Persist failure without sensitive source text or provider response.
            state={**active["data"],"status":"failed","error":type(exc).__name__,"retryable":not isinstance(exc,ValidationError)}
        return self.store.put("job",state,record_id=job["id"],expected_version=active["version"],event_type="JOB_COMPLETED" if state["status"]=="completed" else "JOB_FAILED")

    def retry(self,job_id):
        job=self.store.get(job_id)
        if job["kind"]!="job":raise ValidationError("Expected a workflow job.")
        if job["data"]["status"] not in {"failed","interrupted","pending"}:raise Conflict("Only failed, interrupted or pending jobs can be resumed.")
        if job["data"].get("retryable") is False:raise Conflict("Fix invalid input before starting a new job.")
        return self._execute(job)

    def recover(self):
        recovered=[]
        for job in self.store.list("job"):
            if job["data"].get("status")=="running":
                pid=job["data"].get("worker_pid")
                if isinstance(pid,int) and pid>0:
                    try:
                        os.kill(pid,0)
                        continue
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        continue
                recovered.append(self.store.put("job",{**job["data"],"status":"interrupted","error":"ProcessInterrupted"},
                                                record_id=job["id"],expected_version=job["version"],event_type="JOB_INTERRUPTED"))
        return recovered

