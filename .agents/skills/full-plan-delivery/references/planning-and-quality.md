# Plan from the outcome back to executable evidence

1. Recover the complete approved outcome, audience, existing authorization, explicitly excluded work and non-negotiable constraints. Read every extension, not only the original root. Establish success scenarios and relevant quality dimensions before decomposing implementation.
2. Inventory implemented behavior against the plan. Separate working, partial, absent, unverified and externally blocked criteria. Put live status and decisions in the selected tracker; do not maintain a competing markdown task list. A previously satisfied slice can close only with applicable fresh evidence.
3. Map every approved requirement to at least one actual tracker item and concrete acceptance. `.delivery/mission.json` holds the requirement mapping as specification, not completion state. Changes to scope update both the approved mapping and task graph. Keep deliberate exclusions visible with the decision/evidence reference.
4. Define the smallest useful vertical increments. Each should have a testable behavior or necessary published contract, clear prerequisites and a downstream consumer. Separate design/contract, implementation, integration and outside acceptance where that makes progress possible. Do not split one trivial edit into ceremonial subtasks or generate identical gates for every file.
5. Build the dependency DAG around actual outputs. Distinguish implementation prerequisites from empirical acceptance/release gates. A missing device session should not block unrelated model, UI or account-contract work. A contract change should block its consumers until the agreed version is published.
6. Identify the critical path, ready independent streams, shared integration owners and useful setup prerequisites. Limit WIP. Reconcile original tasks rather than adding duplicate plans indefinitely.

## Task card (store in the live tracker)

```text
Outcome: concrete behavior for a real scenario and its failure/recovery path
Requirement IDs and roadmap root:
Existing behavior/artifacts to reuse:
Prerequisites and exact predecessor outputs:
Acceptance criteria: observable, bounded and domain appropriate
Evidence kinds: automated / independent code review / user / physical / live-service / professional
Read scope and exact source generation:
Write scope and shared integration owner:
Contracts read/published, versions and consumers:
Capabilities and effect/mutation class:
Required quality commands and functional observations:
External blockers: exact criterion, owner, required action; independent work remains eligible
Recovery/rollback and data migration limits:
Output identity, actual evidence, reviewer and next consumer:
```

Use tracker-supported atomic claiming. Merely assigning a label or producing a workcell proposal does not grant a runtime lease or capability. Planned framework adoption remains a proposal until executable mechanisms and evidence support the claim. Keep optional mechanisms explicit; avoid speculative infrastructure that does not help the current project.

## Quality without fictitious scores

Define thresholds from the user's actual goals, current baseline and meaningful comparisons. Apply only relevant dimensions. Examples:

| Dimension | Useful evidence | What cannot replace it |
| --- | --- | --- |
| Functionality | scenario and rejection/recovery checks | files existing or a build alone |
| Usability | users completing key tasks without prompts | an agent asserting “intuitive” |
| Accessibility | semantics, keyboard/assistive-tech checks and sensory choices | color contrast alone |
| Reliability | interruption, retry, concurrency, corrupt/stale-state and recovery checks | the happy path |
| Performance | representative workload, device/service and measured budget | desktop emulation relabeled as a phone |
| Privacy/security | actual access-rule and consent/data-flow checks | secrets present or rules merely written |
| Presentation | reviewed interaction hierarchy, consistency and suitable visual references | repeated cosmetic passes that displace behavior |
| Maintainability | coherent boundaries, contracts and focused verification | speculative microservices or documentation-only conformance |
| Domain validity | the required professional/scientific or real-service evidence | plausible model-generated observations |

Hard gates remain pass/fail/pending. Aesthetic scores may guide critique but cannot average away a failing authorization, data-loss, access-control, evidence or accessibility gate. Record uncertainty and unavailable evidence. If a target is “10/10,” translate it into specific scenarios and standards; do not claim perfection from a private heuristic.

Use a finite critique loop: inspect candidate → identify criterion-based defects → implement → run relevant checks → independent review → integrate. When two passes produce only polishing without material criterion progress, revisit the frontier. Make new review passes explain the specific defect and measurable improvement.

## Acceptance metadata contract

The `complete` command requires each scoped record to be closed and carry this declaration in its **live tracker metadata**. This is evidence metadata, not a second status system. The root declarations must name the current clean integrated candidate. Historical task evidence can reference its own candidate; an independent verifier checks whether it remains applicable after integration.

```json
{
  "delivery": {
    "acceptance": {
      "decision": "accepted",
      "candidate": "git:EXACT-SHA-OR-ARTIFACT-DIGEST",
      "requirements": ["REQ-01"],
      "evidence": [{"ref": "artifact-or-tracker-reference", "outcome": "passed"}],
      "independent_review": {
        "reviewer": "reviewer-identity",
        "builder": "different-builder-identity",
        "ref": "review-reference",
        "decision": "accepted",
        "candidate": "git:SAME-CANDIDATE"
      }
    }
  }
}
```

Use `observed` for properly collected empirical evidence or `accepted` for an accepted review/contract. These fields cannot create an observation or approve a waiver. Store references and aggregate outcomes, never raw private participant data. For trackers without metadata, the explicit adapter must normalize supported structured task fields into this shape; do not infer acceptance from arbitrary comment prose.

Every scoped item needs acceptance evidence. For a requirement mapped to several tasks, at least one mapped acceptance record must explicitly cover its requirement ID; use separate requirement IDs when each constituent needs distinct proof. This does not establish end-to-end success from one local check: the root's current-candidate acceptance and independent integrated review remain required.

On small projects, one root and a few useful slices are enough. Reduce ceremony rather than weakening evidence or dropping scope. Configure independent review as required when it is actually part of the agreed quality bar; never invent a reviewer identity.

