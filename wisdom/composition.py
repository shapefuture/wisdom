"""Explicit composition root for versioned replaceable service slots."""
from pathlib import Path
from .store import Store
from .governance import Governor
from .ingest import IngestService
from .evidence import EvidenceService
from .theory import TheoryEngine
from .invention import InventionEngine
from .learning import DecisionService, OutcomeLab
from .retrieval import RetrievalService
from .memory import MemoryService
from .workflows import WorkflowService
from .watchdog import Watchdog
from .annotations import AnnotationService
from .providers import provider_from_env
from .access import allowed,sources_for
from .errors import PermissionDenied, ValidationError
import json
import hashlib

class ConsentProvider:
    """Typed canonical context gate; raw text or unknown operations cannot select authority."""
    OPERATIONS={"evidence.propose","theory.build","theory.mechanism","invention.diagnose","invention.forge"}
    def __init__(self,store,provider):
        self.store,self.provider=store,provider
        self.name=provider.name
    def _record(self,rid,kind):
        if not isinstance(rid,str) or not rid:raise PermissionDenied("A canonical context record is required.")
        rec=self.store.get(rid)
        if rec["kind"]!=kind or not allowed(self.store,rec,purpose="model"):
            raise PermissionDenied("Canonical context or its ancestry does not permit model sharing.")
        for source in sources_for(self.store,rec):
            data=source['data'];original=data.get('original_text',data.get('text',''))
            if not isinstance(original,str) or hashlib.sha256(original.encode()).hexdigest()!=data.get('content_hash'):
                raise PermissionDenied('Source identity failed content-hash verification.')
        return rec
    def complete(self,operation,payload):
        if operation not in self.OPERATIONS:
            raise PermissionDenied("Unknown model operations and raw-text passthrough are forbidden.")
        if not isinstance(payload,dict):raise ValidationError("Model input must be a typed object.")
        if operation=="evidence.propose":
            source=self._record(payload.get("source_id"),"source")
            spans=payload.get("spans")
            if not isinstance(spans,list) or not spans:raise PermissionDenied("Canonical source spans are required.")
            canonical=[]
            for item in spans:
                if not isinstance(item,dict):raise PermissionDenied("Invalid source span.")
                span=self._record(item.get("id"),"span")
                if span["data"].get("source_id")!=source["id"] or item.get("text")!=span["data"].get("text"):
                    raise PermissionDenied("Model span data do not match the approved canonical source.")
                d=span['data'];original=source['data'].get('original_text',source['data'].get('text',''))
                start,end=d.get('start_char'),d.get('end_char')
                if not isinstance(start,int) or not isinstance(end,int) or start<0 or end<start or original[start:end]!=d['text']:
                    raise PermissionDenied('Source span failed exact original verification.')
                canonical.append({"id":span["id"],"text":span["data"]["text"]})
            safe={"source_id":source["id"],"source_title":source["data"].get("title"),"spans":canonical,"schema":"evidence-proposals-v1"}
        elif operation.startswith("theory."):
            if payload.get("allow_model") is not True:
                raise PermissionDenied("User-entered theory context requires explicit model-sharing consent.")
            ids=payload.get("claim_ids",[])
            if not isinstance(ids,list):raise ValidationError("claim_ids must be a list.")
            claims=[self._record(rid,"claim") for rid in ids]
            fields={"title","claim_ids","scope","explanation","counterexamples","predictions","evidence_for","evidence_against",
                    "alternatives","preconditions","failure_conditions","open_questions","generalization","mechanism",
                    "problem_state","intervention","effects","boundary_conditions","contraindications","functional_signature",
                    "structural_signature","source_domain","theory_id"}
            safe={k:v for k,v in payload.items() if k in fields}
            if payload.get("theory_id"):
                theory=self._record(payload["theory_id"],"theory")
                safe["source_theory"]={"id":theory["id"],"data":theory["data"]}
            safe["source_claims"]=[{"id":r["id"],"data":r["data"]} for r in claims]
        else:
            problem=self._record(payload.get("problem_id"),"problem")
            if problem["data"].get("allow_model") is not True:
                raise PermissionDenied("The problem owner has not opted into model processing.")
            safe={"problem_id":problem["id"],"problem":problem["data"]}
            if operation=="invention.forge":
                candidates=payload.get("candidate_mechanisms",[])
                if not isinstance(candidates,list):raise ValidationError("Mechanism candidates must be a list.")
                canonical=[]
                for candidate in candidates:
                    if not isinstance(candidate,dict):raise PermissionDenied("Canonical mechanism IDs are required.")
                    mechanism=self._record(candidate.get("id"),"mechanism")
                    canonical.append({"id":mechanism["id"],"data":mechanism["data"]})
                safe["candidate_mechanisms"]=canonical
        encoded=json.dumps(safe,ensure_ascii=False,allow_nan=False)
        if len(encoded)>100000:raise ValidationError("Model input exceeds the configured context boundary; select a smaller source unit.")
        try:
            result=self.provider.complete(operation,safe)
        except Exception as exc:
            self.store.append_event('MODEL_CALL_FAILED',operation,{'model':self.name,'operation':operation,'input_hash':hashlib.sha256(encoded.encode()).hexdigest(),'failure_class':type(exc).__name__})
            raise
        self.store.append_event('MODEL_CALL_COMPLETED',operation,{'model':self.name,'operation':operation,'input_hash':hashlib.sha256(encoded.encode()).hexdigest(),'output_hash':hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()})
        return result

class Application:
    def __init__(self,path=":memory:",*,raw_dir=None,store=None,provider=None,configured_provider=False):
        if store is None and path!=":memory:":
            Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.store=store if store is not None else Store(path,raw_dir=raw_dir)
        if configured_provider:provider=provider_from_env()
        self.provider=ConsentProvider(self.store,provider) if provider is not None else None
        self.governor=Governor(self.store)
        self.ingest=IngestService(self.store)
        self.evidence=EvidenceService(self.store,self.provider)
        self.theory=TheoryEngine(self.store,self.provider)
        self.invention=InventionEngine(self.store,self.provider)
        self.decisions=DecisionService(self.store)
        self.lab=OutcomeLab(self.store)
        self.retrieval=RetrievalService(self.store)
        self.memory=MemoryService(self.store)
        self.watchdog=Watchdog(self.store)
        self.annotations=AnnotationService(self.store)
        self.workflows=WorkflowService(self.store)
        self.workflows.bind("analyze_source",lambda p:self.evidence.analyze(p["source_id"]))
        self.workflows.bind("forge",lambda p:self.invention.forge(p["problem_id"],p))
        self.workflows.bind("compile_context",self.retrieval.compile)
        self.workflows.bind("learn",lambda p:self.lab.learn(p["prediction_id"]))
        self.workflows.recover()
    def close(self):self.store.close()

