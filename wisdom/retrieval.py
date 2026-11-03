"""Inspectable lexical, functional and structural retrieval; no fake embeddings."""
from __future__ import annotations
import hashlib
import json
import re
from .access import allowed, sources_for, references
from .errors import ValidationError, NotFound

def terms(value):
    return set(re.findall(r"[^\W_]+", json.dumps(value,ensure_ascii=False).casefold(),re.UNICODE))

class RetrievalService:
    def __init__(self, store):
        self.store = store

    def search(self, query, lens="semantic", limit=20):
        if not isinstance(query,str) or not query.strip():
            return []
        if lens not in {"semantic","lexical","functional","structural","contradiction","fusion"}:
            raise ValidationError("Unknown retrieval lens.")
        if not isinstance(limit,int) or isinstance(limit,bool) or not 1 <= limit <= 100:
            raise ValidationError("limit must be between 1 and 100.")
        visible = [r for r in self.store.list() if allowed(self.store,r) and r["kind"] not in {"event","job"}]
        q = terms(query)
        keys = {"functional":("functional_signature","intervention","effects","desired_state","maintaining_force"),
                "structural":("structural_signature","actors","constraints","boundary_conditions","problem_state"),
                "contradiction":("counterexamples","evidence_against","contraindications","failed_attempts","rebuttal")}
        def channel(channel_name):
            ranked=[]
            for r in visible:
                d=r["data"]
                text = d if channel_name=="lexical" else {k:d.get(k,[]) for k in keys[channel_name]}
                tokens=terms(text)
                overlap=len(q & tokens)
                if overlap:
                    score=overlap/max(1,len(q)) + overlap/max(1,len(tokens))
                    ranked.append((score,r))
            return sorted(ranked,key=lambda x:(-x[0],x[1]["id"]))
        channels = ["lexical","functional","structural","contradiction"] if lens=="fusion" else ["lexical" if lens=="semantic" else lens]
        ranks={}
        for ch in channels:
            for rank,(_,rec) in enumerate(channel(ch),1):
                ranks.setdefault(rec["id"],{"record":rec,"score":0.0,"channels":[]})
                ranks[rec["id"]]["score"]+=1/(60+rank)
                ranks[rec["id"]]["channels"].append(ch)
        ordered=sorted(ranks.values(),key=lambda x:(-x["score"],x["record"]["id"]))
        return [{**item["record"],"retrieval":{"lens":lens,"channels":item["channels"],"rank_score":item["score"],
                 "method":"lexical_rank_fusion" if lens=="fusion" else "lexical_overlap",
                 "warning":"Ranking is a retrieval heuristic, not evidence confidence."}} for item in ordered[:limit]]

    def compile(self,payload):
        from datetime import datetime,timezone
        question=payload.get("question","")
        budget=payload.get("budget",payload.get("token_budget",2000))
        if not isinstance(question,str) or not question.strip():
            raise ValidationError("A context question is required.")
        if not isinstance(budget,int) or isinstance(budget,bool) or not 128<=budget<=32000:
            raise ValidationError("Context budget must be 128–32000 estimated tokens.")
        cutoff=None
        if payload.get("as_of"):
            try:
                cutoff=datetime.fromisoformat(payload["as_of"].replace("Z","+00:00"))
                if cutoff.tzinfo is None:raise ValueError()
            except (ValueError,TypeError,AttributeError):
                raise ValidationError("as_of must be a timezone-aware ISO 8601 timestamp.") from None
        include_private=payload.get("include_private",True) is True
        candidates=self.search(question,"fusion",100)
        # Reconstruct what was recorded at the decision time, while retaining current access rules.
        if cutoff:
            historical=[]
            q=terms(question)
            for current in self.store.list():
                if not allowed(self.store,current,include_private=include_private):continue
                revisions=[r for r in self.store.history(current["id"])
                           if datetime.fromisoformat(r["updated_at"].replace("Z","+00:00"))<=cutoff]
                if revisions and q.intersection(terms(revisions[-1]["data"])):
                    historical.append(revisions[-1])
            candidates=historical
        selected=[];negative=[];families=set();skipped=0
        packet={"question":question,"task_type":payload.get("task_type","research"),
                "source_evidence":selected,"negative_cases":negative,"missing_evidence":[],
                "source_families":[],"permitted_tools":[],"as_of":payload.get("as_of"),
                "method":"lexical_functional_structural_rank_fusion",
                "staleness":"Snapshot; reopen exact anchors before consequential use.",
                "budget":{"limit":budget,"estimated_tokens":0,"unit":"characters/4 heuristic","omitted":0},
                "packet_version":"0"*64}
        def cost():
            return (len(json.dumps(packet,ensure_ascii=False,sort_keys=True))+3)//4
        if cost()>budget:
            raise ValidationError("The question and required metadata exceed this context budget; shorten the question or increase the budget.")
        def entry(rec):
            if not allowed(self.store,rec,include_private=include_private):return None
            d=rec["data"];srcs=sources_for(self.store,rec)
            if cutoff and any(datetime.fromisoformat(s["created_at"].replace("Z","+00:00"))>cutoff for s in srcs):
                return None
            group=sorted({s["data"].get("source_family") or "content:"+s["data"].get("content_hash",s["id"]) for s in srcs})
            text=d.get("text",d.get("original_text",d.get("reading",d.get("explanation",d.get("proposal","")))))
            item={"id":rec["id"],"kind":rec["kind"],"version":rec["version"],
                  "title":d.get("title",d.get("question",rec["kind"])),
                  "text":text,"epistemic_type":d.get("epistemic_type","unassessed"),
                  "source_ids":[s["id"] for s in srcs],"source_families":group,
                  "uncertainty":d.get("uncertainty","unreviewed"),
                  "review_status":d.get("review_status","not_reviewed"),
                  "qualifiers":d.get("qualifiers",d.get("boundary_conditions",[])),
                  "negative_cases":{k:d[k] for k in ('evidence_against','counterexamples','contraindications','failed_attempts','failure_conditions') if d.get(k)},
                  "open_evidence":"/api/records/"+rec["id"]}
            if d.get("span_ids"):item["span_ids"]=d["span_ids"]
            if d.get("quote") and d["quote"]!=text:item["exact_quote"]=d["quote"]
            if d.get("reviews"):item["latest_review"]=d["reviews"][-1]
            if rec["kind"]=="span":
                item["anchor"]={k:d[k] for k in ("start_char","end_char","start_ms","end_ms","speaker","speaker_uncertain") if k in d}
            return item
        priority={"span":0,"claim":1,"interpretation":2,"argument":2,"theory":3,"mechanism":3,"idea":4,"source":5}
        candidates.sort(key=lambda r:priority.get(r["kind"],6))
        seen_ids=set();deferred=[]
        # Independent witness diversity first, complementary passages from the same family second.
        for rec in candidates:
            item=entry(rec)
            if item is None:continue
            group=set(item["source_families"])
            if group and group.issubset(families):
                deferred.append(item);continue
            selected.append(item)
            if cost()>budget:
                selected.pop();skipped+=1;continue
            seen_ids.add(item["id"]);families.update(group)
        # Negative evidence is retrieved through explicit polarity even if it has no query words.
        for edge in self.store.edges():
            if cutoff and edge.get('created_at') and datetime.fromisoformat(edge['created_at'].replace('Z','+00:00'))>cutoff:
                continue
            if edge["polarity"] not in {"negative","contradiction"} and edge["relation"].upper() not in {"CONTRADICTS","COUNTEREXAMPLE_TO","CONTESTED_BY"}:
                continue
            if not seen_ids.intersection({edge["source_id"],edge["target_id"]}):continue
            for rid in {edge["source_id"],edge["target_id"]}-seen_ids:
                try:record=self.store.get(rid)
                except NotFound:continue
                if cutoff:
                    past=[r for r in self.store.history(rid) if datetime.fromisoformat(r["updated_at"].replace("Z","+00:00"))<=cutoff]
                    if not past:continue
                    record=past[-1]
                item=entry(record)
                if item is None:continue
                item["evidence_relation"]={"relation":edge["relation"],"polarity":edge["polarity"]}
                negative.append(item)
                if cost()>budget:
                    negative.pop();skipped+=1;continue
                seen_ids.add(rid);families.update(item["source_families"])
        for item in deferred:
            if item["id"] in seen_ids:continue
            selected.append(item)
            if cost()>budget:
                selected.pop();skipped+=1;continue
            seen_ids.add(item["id"])
        packet["source_families"]=sorted(families)
        packet["missing_evidence"]=[] if selected else ["No permission-eligible evidence fits the question and budget."]
        packet["budget"]["omitted"]=skipped
        # Metadata is part of the same budget; drop least-priority selected entries if needed.
        while cost()>budget and selected:
            selected.pop()
            packet["budget"]["omitted"]+=1
        if cost()>budget:raise ValidationError("Required context metadata exceed the budget.")
        packet["source_families"]=sorted({f for r in selected+negative for f in r['source_families']})
        packet["missing_evidence"]=[] if selected else ["No permission-eligible evidence fits the question and budget."]
        for _ in range(3):packet["budget"]["estimated_tokens"]=cost()
        while cost()>budget and (selected or negative):
            (selected if selected else negative).pop()
            packet["budget"]["omitted"]+=1
            for _ in range(3):packet["budget"]["estimated_tokens"]=cost()
        if cost()>budget:raise ValidationError("Required context metadata exceed the budget.")
        version_basis=[(r["id"],r["version"]) for r in selected+negative]
        if not cutoff:version_basis.extend((r["id"],r["version"]) for r in self.store.list())
        packet["packet_version"]=hashlib.sha256(json.dumps([packet,version_basis],sort_keys=True).encode()).hexdigest()
        self.store.append_event("CONTEXT_COMPILED",packet["packet_version"],
            {"question_hash":hashlib.sha256(question.encode()).hexdigest(),"record_ids":[r['id'] for r in selected+negative],"estimated_tokens":packet["budget"]["estimated_tokens"]})
        return packet

    def lineage(self,record_id):
        root=self.store.get(record_id)
        if not allowed(self.store,root):
            raise NotFound("Record is unavailable for this purpose.")
        pending=[root];seen={};edges=[];gaps=[]
        all_edges=self.store.edges()
        while pending and len(seen)<200:
            r=pending.pop()
            if r["id"] in seen:continue
            seen[r["id"]]=r
            related=[e for e in all_edges if e["source_id"]==r["id"]]
            ids=references(r["data"])+[e["target_id"] for e in related]
            for target in dict.fromkeys(ids):
                try:
                    next_record=self.store.get(target)
                    if allowed(self.store,next_record):
                        pending.append(next_record)
                    else:gaps.append({"id":target,"reason":"Source permission/expiry restriction"})
                except NotFound:
                    gaps.append({"id":target,"reason":"Missing or deleted dependency"})
            edges.extend(related)
        visible=set(seen)
        edges=[e for e in edges if e["source_id"] in visible and e["target_id"] in visible]
        if not any(r["kind"]=="source" for r in seen.values()):
            gaps.append({"id":record_id,"reason":"No original source anchor in this lineage; generated or human-entered record."})
        return {"nodes":list(seen.values()),"edges":edges,"gaps":gaps}

