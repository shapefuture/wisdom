# WF-AUDIT-RUNTIME: retrieval, workflows, provider, access, watchdog

**Candidate:** frozen commit `40312598dbf10dbc351ca8a3148966d5336dd5ad`  
**Verdict:** **Not ready for runtime acceptance.** Context history, budget accounting, explicit contradiction edges, and workflow retries work in the tested paths. Two P1 privacy/access defects remain in the shared provider/access boundary. Additional P2 correctness and monitoring gaps are listed below.

The audit was read-only against an in-memory Store. No live provider, browser, human review, or production system was available or exercised.

## Checks run

- `python -m unittest discover -s tests -v`: **94 passed**.
- `python tools/architecture_check.py`: **passed**, five checks (adapter isolation, StorePort completeness, constitution, logical slots, 22-section coverage).
- Adversarial in-memory probes covered provider consent, source status/rights, historical cutoff, negative evidence, source-family grouping, final context budget, and concurrent same-key workflow runs.

## Findings

### P1 — `ConsentProvider` can send source content without checking consent

At `wisdom/composition.py:24–31`, the provider wrapper serializes the payload and looks for stored record IDs as substrings. It does not require source IDs or resolve ancestry from an explicit trusted argument. A caller can pass source text without its ID and bypass the wrapper.

Reproduction against the frozen candidate:

```python
source = store.put("source", {
    "text": "classified", "original_text": "classified",
    "rights": {"allowed": True, "private": True,
              "allow_model": False, "allow_export": False}
})
sink = FakeProvider()
ConsentProvider(store, sink).complete("test.op", {"raw_text": "classified"})
# sink.calls contains {"raw_text": "classified"}
```

This is a provider-boundary consent bypass even though the existing evidence-service consent test passes. Fix by requiring explicit source references at the provider boundary and checking their full ancestry; service-specific filtering alone does not protect future or alternate callers.

### P1 — Poisoned, quarantined, and lowercase-expired sources pass the shared access gate

`wisdom/access.py:48–68` checks source rights and only exact uppercase `BLOCKED`/`EXPIRED` values. It does not reject `poisoned`, `quarantined`, or `security_status` markers. A source with `status="expired"` also passes. Since both retrieval and `ConsentProvider` call this helper, affected derived records are searchable and may be model-shared when `allow_model` is true.

Reproduction: create a source with affirmative rights and one of `poisoned=True`, `security_status="quarantined"`, or lowercase `status="expired"`; create a claim that references it. For each case, `allowed(store, claim, purpose="model")` returned `True`, and lexical search returned both records.

Normalize status comparisons and fail closed on all recorded quarantine/poisoning flags. Make `rights` a validated mapping; `rights=None` currently raises `AttributeError` in `allowed()` instead of returning a denial.

### P2 — Missing source ancestry is silently treated as permission-eligible

`wisdom/access.py:27–45` catches `NotFound` while traversing references and drops that edge. A claim with `source_id="missing-source"` therefore has no resolved sources, so `allowed()` returns `True`; retrieval returns the claim. This also means `rights=None` can produce a runtime exception rather than a clean refusal.

The Store purge path cascades normal source deletion, so the orphan case needs malformed/imported or incomplete records, but the shared access helper should treat an unresolved declared source reference as a gap/denial rather than as a source-free record.

### P2 — Inline `evidence_against` is omitted from compiled negative cases

`wisdom/retrieval.py:103–106` builds `negative_cases` from only `counterexamples`, `contraindications`, or `failed_attempts`. It does not include `evidence_against`. The edge-based recovery at lines 127–147 works when a `CONTRADICTS`/negative link exists, as the existing runtime test demonstrates; the inline field itself disappears if that link is absent or malformed.

Reproduction: compile a matched theory with `{"evidence_against": ["No effect under the stated condition"]}` and no contradiction edge. Its packet entry has `negative_cases=[]` and no `evidence_against` field. Preserve all negative fields independently and merge rather than selecting the first present field.

### P2 — Concurrent duplicate workflow request can return a spurious conflict

`wisdom/workflows.py:36–50` checks for an idempotency key before the Store’s atomic put, then both callers may execute the same pending job envelope. `_execute()` uses compare-and-swap at lines 52–56; the loser receives a `Conflict` while the winning request completes the shared job.

Reproduction used two threads and a barrier forcing both prechecks to see no existing job. One call returned the completed job; the other raised `Conflict: version conflict: current version is 2`. Only one handler execution occurred and one completed job remained, so this did **not** duplicate the side effect. The idempotency key protects execution, but concurrent API callers do not consistently receive the same job/result. Consider re-reading and returning the winning job when the CAS loses to an identical fingerprint.

### P2 — Watchdog does not audit access/quarantine invariants

`wisdom/watchdog.py:11–32` checks ledger validity, span anchoring, claim span presence, generated epistemic labels, and skill authorization. It does not inspect rights/status on source ancestry, malformed or unresolved references, poisoning/quarantine flags, or context/provider consent. The two P1 defects above therefore do not appear in its audit findings. This is a coverage limitation, not evidence that the watchdog incorrectly reports its present checks; expand the audit or label this assurance scope clearly.

## Verified behavior and limits

- **Historical context:** the supplied test returns the prior claim version; an additional cutoff probe excluded a record created after `as_of`. Current access rights are still applied during historical compilation, as required by the contract.
- **Budget:** output reports the characters/4 estimate and stayed within the requested budget in sampled packets; at 128 estimated tokens it refused when mandatory metadata could not fit. This is the documented estimate, not tokenizer accuracy.
- **Source families:** duplicate source records with one family were both visible with the same family label, while the packet’s family set contained the family only once. The compiler prioritizes family diversity but does not collapse same-family records; consumers should not count record count as independent corroboration.
- **Negative evidence:** explicit negative edges are included even without query-word overlap when attached to a matched record; see the inline-field gap above.
- **Retrieval semantics:** the “semantic” lens is explicitly reported as `lexical_overlap`; fusion is lexical rank fusion. No embedding scores or semantic authority are fabricated.
- **Workflow authority:** the composed application binds local analysis, invention, context, and learning handlers. Routing is marked advisory-only; the configured JSON provider has no tool/execution API. No external action executor was observed in these audited components.
- **Provider/human/browser:** provider transport and model quality were not tested live. Browser rendering and independent human assessment remain unverified; no outcome or benchmark claim is made.
