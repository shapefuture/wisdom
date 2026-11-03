# Antifragile Adaptive Architecture v7.1
## Agent-Native Universal Governed Evolution Kernel

Status: Draft normative specification
Version: 7.1.0
Scope: General-purpose software systems. Agentic development is mandatory and native; agentic/LLM behavior in the shipped runtime is optional and gated.

## 0. Normative language

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY, and OPTIONAL are normative.

This specification separates a small universal runtime kernel, a mandatory Agentic Development Fabric, and optional runtime profiles. A conforming implementation may be a monolith, CLI, desktop app, embedded controller, data pipeline, distributed service, game, mobile application, or AI agent system. No LLM, Kubernetes, microservice, event sourcing, or cloud dependency is assumed by the shipped runtime core. Development, however, is always structured so independent agents or fleets of agents can work in isolated workcells and integrate through machine-checkable contracts.

## 1. Design goal

A system conforming to AAA v7.1 SHALL be able to answer, mechanically where feasible:

1. What must never become false?
2. What is authoritative state, and how is it recovered?
3. Which effects may occur, with what authority, and how are they reversed or compensated?
4. What exact generation is running?
5. What evidence justified activating it?
6. What changed relative to its parent generation?
7. What is the smallest dependency cone invalidated by a change or failure?
8. Which adaptations may happen autonomously, and which require coordination or approval?
9. How does the system return to a legitimate state after bounded faults?
10. Which optional runtime adaptation or agentic mechanisms are currently enabled?
11. Which development workcells own each change, what may they write, and can they execute in parallel without interference?
12. Can any replaceable component be swapped for another conforming implementation without modifying its consumers?

The system SHALL prefer preservation of valid work over global reset and SHALL prefer the least powerful mechanism that solves the problem.

## 2. First principles

AAA v7.1 is based on thirteen principles.

### P1. Minimal privileged kernel

Only mechanisms required to protect invariants, authority, generation identity, evidence integrity, and safe transitions belong in the privileged kernel. Everything else SHOULD be replaceable.

### P2. Separation of authority

Execution authority, evaluation authority, deployment authority, and evidence authority MUST be separable. No component may unilaterally change the mechanism that determines its own success, authority, deployment, or evidence.

### P3. Immutable generations

A meaningful software change creates a new generation. A running generation MUST NOT silently rewrite its own identity. Promotion changes an active pointer to an already-built generation.

### P4. Minimal disturbance

A change, failure, rollback, or optimization SHOULD invalidate only the smallest causally dependent subgraph that can no longer be trusted.

### P5. Reconstructibility

Anything used to make a high-consequence adaptive decision MUST be attributable to authoritative or reconstructible state.

### P6. Effects are typed

The architecture SHALL distinguish pure computation, reads, monotone writes, reversible writes, idempotent external effects, and irreversible external effects. Retry, speculation, rollback, and coordination policy depend on the effect class.

### P7. Bounded adaptation

Autonomy is a capability, not a default. Every adaptation loop operates inside explicit authority, budget, risk, and time bounds.

### P8. Verification before persistence

Transient observations, diagnoses, or generated changes MUST NOT become persistent trusted behavior merely because the generating component believes them to be correct.

### P9. Self-stabilization target

For systems declaring adaptive or recovery behavior, the legitimate-state predicate and convergence target MUST be explicit.

### P10. Monotonicity before coordination

Monotone or commutative updates MAY use coordination-free mechanisms where semantics allow. Non-monotone decisions and irreversible global effects MUST cross an explicit coordination or fencing boundary.

### P11. Complexity must pay rent

Persistent architecture, policy, workflow, or adaptation machinery SHOULD be removable unless evidence shows useful marginal value.

### P12. Agent-native development isolation

Every conforming project MUST be decomposable into machine-described development workcells that can be assigned to independent agents or fleets. Workcells MUST NOT coordinate through a shared mutable workspace. Parallel work communicates through immutable inputs, versioned contracts, immutable artifacts, and explicit integration transactions.

### P13. Contract-bound swappability

Consumers MUST depend on logical component slots and versioned contracts, never on a concrete implementation except at a declared composition root. A conforming alternative implementation that passes the slot's compatibility, state, effect, and contract gates MUST be swappable by changing generation binding rather than consumer code.

## 3. Universal architecture

AAA v7.1 is not a linear layer stack. It is a small governed runtime kernel fed by a mandatory agent-native development fabric. Runtime agenticity remains optional.

```text
                     DEVELOPMENT TIME
+---------------------------------------------------------------------+
|              AGENTIC DEVELOPMENT FABRIC (MANDATORY)                 |
| task/conflict DAG | workcell isolation | leases | contract registry |
| candidate builder | integration broker | independent verification   |
+------------------------------+--------------------------------------+
                               | immutable candidate generations
                               v
+---------------------------------------------------------------------+
|                         CONSTITUTION                                |
| hard invariants | authority ceiling | risk policy | dev isolation   |
+------------------------------+--------------------------------------+
                               |
+------------------------------v--------------------------------------+
|                  UNIVERSAL GOVERNED RUNTIME KERNEL                   |
| generation manager | authority broker | evidence validator          |
| transition manager | control journal | composition bindings         |
+------------+------------------+------------------+-------------------+
             |                  |                  |
      +------v------+    +------v------+    +------v------+
      | EXECUTION   |    | STATE       |    | EFFECT      |
      | PLANE       |    | PLANE       |    | PLANE       |
      +-------------+    +-------------+    +-------------+
             |                  |                  |
      +------v------------------v------------------v------+
      |                  OPTIONAL RUNTIME PROFILES         |
      | resilience | distributed | incremental | adaptive |
      | plugin-runtime | safety-critical | runtime-agentic |
      +----------------------------------------------------+
```

Logical separation is REQUIRED. Physical separation is profile-dependent. The development fabric exists for every conforming program, even when the runtime-agentic profile is AG0.

## 4. Formal system model

A system state at time t is:

```text
X_t = (G_t, S_t, E_t, A_t, K_t, P_t)
```

where:

- `G_t`: active immutable generation.
- `S_t`: authoritative operational/domain state.
- `E_t`: effect ledger and externally committed effects.
- `A_t`: current authority/capability assignments.
- `K_t`: knowledge and derived projections used by control loops.
- `P_t`: enabled profiles and runtime configuration.

A transition is:

```text
T : X_t x Input x Capability -> X_(t+1) x Effects x Evidence
```

A transition is admissible only if all hard constitutional invariants remain satisfied or the transition is an explicitly authorized recovery transition that converges toward a legitimate state.

### 4.1 Legitimate state

Each adaptive or self-healing system MUST define a predicate `L(X)` describing legitimate states.

Strong self-stabilization target:

```text
Convergence:  from every state in the declared fault envelope F,
              eventually L(X) becomes true within stabilization bound B.

Closure:      if L(X) is true and no new declared fault occurs,
              allowed transitions preserve L(X).
```

The specification MAY weaken this to probabilistic or best-effort convergence, but the weakening MUST be explicit.

## 5. Constitution

The constitution is the highest-trust specification.

It contains:

```yaml
constitution:
  invariants: []
  authority_ceiling: {}
  forbidden_transitions: []
  risk_policy: {}
  emergency_policy: {}
```

### 5.1 Invariant classes

- `hard`: activation or runtime transition MUST be blocked if violated.
- `recoverable`: temporary violation is allowed only inside an explicit recovery transaction with a convergence bound.
- `soft`: optimization target or preference, never a substitute for a hard gate.

Example:

```yaml
- id: no-negative-balance
  class: hard
  scope: domain
  expression: "account.balance >= 0"
  verifier: property-test://ledger/non_negative
```

### 5.2 Authority ceiling

The constitution MUST define capabilities that no unprivileged component may self-grant.

Examples:

- changing hard invariants,
- modifying root evaluator secrets,
- deleting audit/evidence history,
- granting root credentials,
- bypassing activation gates,
- widening its own capability ceiling.

## 6. Authority model

AAA v7.1 uses explicit capabilities rather than ambient authority.

A capability has:

```text
Capability = {
  principal,
  action,
  resource,
  constraints,
  expiry,
  max_uses,
  delegation_policy
}
```

A component MUST NOT receive a credential or authority broader than necessary for its declared effects.

### 6.1 Authority lattice

Recommended authority order:

```text
OBSERVE < ANNOTATE < PROPOSE < RESTRICT < DENY < EXECUTE
        < REDIRECT < REWRITE < REPLACE < PROMOTE < GOVERN
```

Components SHOULD receive the weakest sufficient authority.

### 6.2 Four-authority rule

For R3 and R4 changes, these roles MUST be independently controllable:

1. Candidate producer.
2. Evaluator.
3. Activator/deployer.
4. Evidence/provenance authority.

A single process MAY implement multiple roles only in low-risk profiles and only when the constitution explicitly permits it.

## 7. Immutable generation model

Every meaningful deployable state SHALL have a `GenerationManifest`.

```text
GenerationManifest {
  generation_id,
  parent_ids[],
  source_hash,
  build_hash,
  dependency_lock_hash,
  configuration_hash,
  schema_hashes[],
  policy_hash,
  component_graph_hash,
  feature_configuration_hash,
  evidence_root,
  created_at,
  signer
}
```

`generation_id` SHOULD be content-addressed.

Activation MUST be atomic from the control plane perspective:

```text
active_generation := candidate_generation
```

The previous generation SHALL remain addressable for rollback unless retention policy explicitly permits its removal after the rollback horizon.

## 8. Component and capability bundles

Replaceable components SHOULD declare a machine-readable manifest.

```yaml
component:
  id: payments.v2
  provides: [payment.authorize]
  requires: [ledger.read, gateway.charge]
  interfaces:
    - contract: api/payment/v2
  capabilities:
    - charge:gateway:merchant-42
  effects:
    - class: E4_IDEMPOTENT_EXTERNAL
      operation: gateway.charge
  lifecycle:
    install: hooks/install
    start: hooks/start
    quiesce: hooks/quiesce
    stop: hooks/stop
    uninstall: hooks/uninstall
    rollback: hooks/rollback
  state:
    migration: migrations/v2
    recovery: replayable
```

### 8.1 Reversible composition

Where runtime installation/uninstallation is supported, installation SHOULD be treated transactionally:

```text
resolve -> authorize -> stage -> apply effects -> verify -> commit
```

Failure before commit SHALL trigger inverse effects or compensation where declared.

## 9. Effect system

All externally visible or state-mutating operations SHOULD be classified.

| Class | Name | Typical examples | Retry | Speculation | Rollback |
|---|---|---|---|---|---|
| E0 | PURE | calculation | yes | yes | unnecessary |
| E1 | READ | database/API read | bounded | often | unnecessary |
| E2 | MONOTONE_WRITE | append fact, add set member | idempotent/merge | limited | logical compensation |
| E3 | REVERSIBLE_WRITE | reversible config change | bounded | sandbox only | inverse effect |
| E4 | IDEMPOTENT_EXTERNAL | payment API with idempotency key | policy-bound | no by default | provider/domain compensation |
| E5 | IRREVERSIBLE_EXTERNAL | email send, physical action | no blind retry | prohibited | compensation may be impossible |

Every E4/E5 effect MUST carry an `effect_id` or equivalent deduplication/fencing identity when the external system permits it.

### 9.1 Effect ledger

High-consequence effects SHOULD use intent/commit records:

```text
EffectIntent(effect_id, operation, target, parameters_hash)
EffectCommitted(effect_id, external_reference)
EffectCompensated(effect_id, reason)
```

This prevents recovery replay from silently duplicating external effects.

## 10. State strategy

AAA v7.1 does not mandate event sourcing.

A system MUST declare one or more authoritative state strategies:

- `mutable_transactional_store`
- `append_only_event_store`
- `durable_workflow_journal`
- `immutable_fact_store`
- `replicated_crdt`
- `hybrid`

For each authoritative state class, declare:

```yaml
state:
  authority: postgres
  durability:
    acknowledgement: quorum_commit
    rpo: 0s
    rto: 60s
  recovery:
    strategy: wal_plus_snapshot
    validation: state_hash
```

### 10.1 Mandatory control journal

Even when business/domain state is not event sourced, the architecture control plane MUST maintain an append-only or tamper-evident journal for:

- generation creation,
- activation and rollback,
- policy/evaluator versions,
- authority changes,
- incidents,
- adaptation actions,
- evidence roots.

## 11. Domain isolation

Business semantics SHOULD remain independent from infrastructure implementation.

A default profile uses:

```text
Adapters -> Ports -> Domain
```

Domain code SHOULD NOT depend directly on databases, queues, HTTP libraries, UI frameworks, orchestration frameworks, or agent frameworks.

Architecture fitness checks SHOULD enforce dependency direction.

## 11A. Agentic Development Fabric (mandatory)

AAA v7.1 is agentic-development-native for every project. This is independent of whether the shipped program contains an agent or LLM.

The development fabric MUST provide five logical services:

1. `Task Graph Compiler`: decomposes intended changes into dependency and conflict-aware work items.
2. `Workcell Manager`: creates isolated development environments pinned to an immutable base generation.
3. `Contract Registry`: stores versioned component-slot, API, schema, effect, and state contracts.
4. `Integration Broker`: composes completed workcell outputs into candidate generations without allowing workers to write directly to the active integration state.
5. `Independent Verifier`: reruns the required gates in a clean environment and emits evidence owned outside the producing workcell.

A human developer, one coding agent, a subagent tree, or an entire fleet may be the principal inside a workcell. The isolation semantics are identical.

### 11A.1 Development state

Development state is separate from runtime state:

```text
Dev_t = (B_t, Q_t, W_t, C_t, L_t, I_t)
```

where:

- `B_t`: immutable base/integration generation.
- `Q_t`: task/dependency/conflict graph.
- `W_t`: active isolated workcells.
- `C_t`: versioned contract and component-slot registry.
- `L_t`: ownership/write leases.
- `I_t`: integration queue and candidate-generation set.

No workcell-local scratch state is authoritative outside that workcell until committed as an immutable artifact and accepted by the integration broker.

### 11A.2 Workcell contract

Every work item MUST be representable as:

```yaml
workcell:
  id: wc-search-ranking-17
  base_generation: sha256:...
  task_node: task://ranking/new-scorer
  principals: [fleet://ranking-agents]
  read_set:
    - contracts/search/**
    - components/query-parser/**
  write_set:
    - components/ranking/new-scorer/**
  owned_slots:
    - search.ranker
  capabilities:
    - repo.read
    - tests.execute
    - artifact.publish:candidate
  forbidden:
    - active_generation.write
    - evidence_root.write
    - other_workcell.write
  outputs:
    - candidate_component
    - contract_test_results
    - change_manifest
```

Workcell capabilities MUST be narrower than production capabilities unless a risk gate explicitly authorizes otherwise.

### 11A.3 No shared mutable workspace

Two concurrently executing workcells MUST NOT mutate the same working directory, checkout, database schema, mutable fixture set, generated-code cache, or unversioned integration environment.

Permitted coordination channels are:

- immutable repository base generation,
- versioned contracts,
- immutable artifacts/content hashes,
- append-only task/evidence events,
- explicit messages whose payload is recorded in the task journal.

Shared caches MAY exist only when cache writes cannot change semantic outputs or when entries are content-addressed and immutable.

A Git branch alone is not sufficient isolation if agents share the same mutable worktree, environment, database, or generated artifacts. Worktrees/containers/VMs/sandboxes MAY implement workcells, but the semantic requirement is isolation, not a specific tool.

## 11B. Parallel-safe development

Let each task `i` have:

```text
R_i = declared read set
W_i = declared write set
O_i = owned component/state slots
K_i = contract versions consumed or changed
D_i = predecessor tasks
```

Two ready tasks `i` and `j` are parallel-safe only if:

```text
W_i intersection W_j = empty
W_i intersection R_j = empty, unless R_j is pinned to immutable base content
W_j intersection R_i = empty, unless R_i is pinned to immutable base content
O_i intersection O_j = empty
no incompatible contract transition exists between K_i and K_j
all predecessor constraints are satisfied
```

The Task Graph Compiler MUST derive a conflict graph in addition to the ordinary dependency DAG.

```text
Dependency edge: B needs output from A.
Conflict edge: A and B could run independently logically, but may not mutate overlapping authority/state/contracts concurrently.
```

A scheduler MAY parallelize any ready antichain of the combined dependency/conflict graph.

### 11B.1 Same-component fleets

Multiple agents MAY explore alternatives for the same component only as isolated competing candidates:

```text
base component
   |\
   | +-> candidate B in workcell B
   +----> candidate A in workcell A
```

They MUST NOT cooperatively edit the same mutable candidate tree. Their results meet only at evaluation/integration, where one candidate, an explicit merge, or neither is selected.

### 11B.2 Contract-change fanout

A workcell MUST NOT silently edit a shared contract to make its implementation pass.

A contract change creates a new contract version and a fanout plan:

```text
contract v1 -> proposed v2
                  |
                  +-> producer migration task
                  +-> consumer A compatibility task
                  +-> consumer B compatibility task
                  +-> state/schema migration task, if any
```

The old contract remains immutable. This is the primary mechanism that lets fleets work independently without a moving floor beneath them.

## 11C. Component slots and implementation swappability

AAA v7.1 distinguishes a logical `ComponentSlot` from concrete implementations.

```yaml
slot:
  id: search.ranker
  contract: contract://search/ranker/v3
  cardinality: one
  state_owner: ranking-state
  effect_ceiling: E1_READ
  selection: manifest_binding
  compatibility_suite: testkit://search/ranker/v3
```

Implementations declare:

```yaml
component:
  id: search.ranker.bm25
  implements: search.ranker
  contract: contract://search/ranker/v3
  artifact: oci://...@sha256:...
  state_migration: migration://ranking/v2-v3
```

Consumers MUST import/reference the slot contract, never `search.ranker.bm25` directly. Concrete binding is allowed only in the composition root or generation manifest.

### 11C.1 Swap protocol

Replacing implementation `A` with `B` SHOULD require only:

1. `B` declares the same slot and a compatible contract version.
2. `B` passes the slot's contract and effect tests in isolation.
3. Stateful slots pass migration, replay, and rollback/forward-compatibility checks required by risk class.
4. The impact engine proves consumers depend only on the unchanged contract, or identifies the minimal affected cone.
5. A new generation binds the slot to `B`.
6. The normal risk-selected verification and activation ladder runs.

If consumer source code must change solely because the implementation changed, the slot boundary is considered coupled and the architecture fitness gate SHOULD fail.

### 11C.2 Swap dimensions

Swappability MUST be evaluated separately across:

- `interface`: API/schema/behavior compatibility,
- `state`: ownership and migration compatibility,
- `effects`: same or narrower effect/authority ceiling,
- `operations`: deployability and observability,
- `performance`: declared SLO envelope,
- `failure semantics`: timeout/retry/fallback expectations.

A component that matches method signatures but violates these dimensions is not a conforming substitute.

### 11C.3 Composition root

Every deployable program MUST have an explicit composition root that resolves:

```text
logical slot -> concrete implementation generation
```

The binding table is part of the `GenerationManifest` and MUST therefore be attributable, diffable, and rollbackable.

## 11D. Agent-fleet integration transaction

Agent-produced code never becomes authoritative by direct merge to the active generation.

The normative flow is:

```text
Task DAG
  -> isolated workcells/fleets
  -> immutable candidate artifacts
  -> local contract evidence
  -> Integration Broker
  -> clean composition candidate
  -> independent verification
  -> candidate generation
  -> normal activation gates
```

The Integration Broker MUST reject at least:

- overlapping undeclared writes,
- stale base assumptions affecting changed contracts,
- hidden concrete-component dependencies,
- missing slot contracts,
- unauthorized authority expansion,
- incompatible state ownership,
- non-reproducible generated artifacts,
- evidence produced only by the candidate when independent evidence is required.

Parallelism is therefore optimistic at development time but serialized only at the smallest necessary integration boundary.

## 12. Resilience contracts

AAA v7.1 rejects a universal fixed middleware chain.

Every external operation declares a `ResilienceContract` appropriate to its semantics.

```yaml
operation: inventory.lookup
class: E1_READ
resilience:
  admission:
    mode: adaptive_concurrency
    min: 4
    max: 200
  deadline_ms: 250
  retry:
    max_attempts: 2
    budget: 0.05
    backoff: exponential_jitter
  circuit:
    enabled: true
  fallback:
    strategy: bounded_stale_cache
    max_age_ms: 5000
```

For E4/E5 operations, blind fallback and retry MAY be forbidden.

### 12.1 Admission before exhaustion

Every bounded resource SHOULD have admission control before unbounded queue growth can occur.

Static limits MAY be used. Adaptive concurrency is RECOMMENDED where workload variability justifies it.

## 13. Coordination compiler

Every distributed mutation SHOULD be classified by algebraic semantics.

### C0. Monotone

New information cannot invalidate previous accepted information.

Coordination-free execution MAY be allowed.

### C1. Commutative/mergeable

Concurrent operations converge by a deterministic merge or CRDT-like join.

Coordination MAY be avoided subject to declared invariants.

### C2. Non-monotone

New information may retract or invalidate previous conclusions.

Explicit coordination, quorum, lock, transaction, or equivalent fencing is REQUIRED when correctness depends on a global fact.

### C3. Irreversible/global

External irreversible effect, authority change, or globally unique decision.

Strong fencing/serialization and evidence are REQUIRED.

This classification should be derived automatically where practical and declared otherwise.

## 14. Runtime reflection model

Systems enabling adaptation SHOULD maintain a causally connected runtime model with at least:

```text
DesiredState
ObservedState
AuthoritativeState
DerivedState
```

Differences between desired and observed state drive reconciliation.

Changing a runtime model MUST NOT bypass the same authority and transition rules as direct changes to the running system.

## 15. Adaptation model

AAA v7.1 uses four logically separate loops.

### 15.1 Runtime control loop

Fast loop for bounded operating changes such as routing, concurrency, cache mode, or resource allocation.

### 15.2 Recovery loop

Restores legitimate state after detected faults.

### 15.3 Evolution loop

Creates new immutable generations that change implementation, configuration, schema, algorithms, or policies.

### 15.4 Assurance loop

Independently checks whether claims are still supported by current evidence and runtime observations.

No loop may silently acquire authority belonging to another loop.

## 16. Runtime assurance and safe baseline

For R3/R4 adaptive behavior, a Simplex-style pattern is RECOMMENDED and MAY be REQUIRED by policy.

```text
Advanced controller
        |
        v
Independent decision module
     /       \
  safe       unsafe
   |            |
   v            v
advanced     verified or known-good baseline
```

Every high-risk adaptive controller SHOULD declare:

- baseline controller/configuration,
- switch-to-baseline condition,
- return-to-advanced condition,
- recovery horizon,
- evidence that baseline preserves the required safety envelope.

## 17. Variability and feature model

Programs with substantial runtime variability SHOULD enable the `variability` profile.

A feature model declares:

```text
features
requires constraints
excludes constraints
cardinality constraints
context constraints
```

Only valid configurations may be activated.

Configuration changes SHOULD be checked with SAT/SMT or equivalent constraint validation before activation.

Dynamic feature changes SHOULD be treated as generation or configuration transactions rather than arbitrary runtime mutation.

## 18. Dependency and incremental profile

When computation or derived state is expensive, enable the `incremental` profile.

The system maintains a dependency graph:

```text
input/version -> derived node -> downstream nodes
```

On change:

1. Compute the affected causal cone.
2. Mark only dependent nodes dirty.
3. Preserve unaffected verified nodes.
4. Recompute lazily or according to priority.
5. Revalidate downstream claims whose evidence depended on invalidated nodes.

This profile may use build-system, self-adjusting-computation, Datalog, or differential-dataflow techniques.

## 19. Architecture conformance

Architecture rules MUST be executable where practical.

Typical hard checks:

- forbidden dependency edges,
- cyclic dependency restrictions,
- domain-to-infrastructure import violations,
- missing effect declaration,
- undeclared capabilities,
- incompatible interface versions,
- unvalidated runtime feature configuration,
- missing rollback/compensation for required classes,
- candidate/evaluator authority collision,
- unsigned high-risk evidence bundle,
- overlapping active workcell write/ownership leases,
- direct consumer dependency on a concrete swappable implementation,
- mutable cross-workcell communication channel,
- contract modification without a new version/fanout analysis,
- component slot lacking a compatibility suite or explicit sealed exemption.

A numerical architecture score MAY be produced for diagnosis. It MUST NOT substitute for hard gates.

## 20. Change classes

Every proposed change receives a mutation class.

| Class | Description | Examples |
|---|---|---|
| M0 | Semantics-preserving structural | caching, parallelization, refactor |
| M1 | Behavioral | algorithm, prompt-independent policy, UX behavior |
| M2 | State/schema | schema, serialization, migration |
| M3 | External-effect/authority | payments, permissions, irreversible integrations |
| M4 | Governance/meta | evaluator, promotion policy, constitutional mechanism |

M4 is denied to unprivileged evolution by default.

## 21. Risk classes

| Risk | Meaning | Minimum gate |
|---|---|---|
| R0 | pure/local/reversible | static + unit/property checks |
| R1 | ordinary application behavior | contract + regression |
| R2 | persistent state or distributed behavior | replay/migration + integration |
| R3 | money, security, privacy, external irreversible effect | independent evaluator + shadow/canary + rollback/baseline |
| R4 | safety-critical, governance, authority, self-improvement machinery | formal/model assurance where feasible + independent evidence authority + explicit approval |

Risk class is the maximum of component risk, effect class, and mutation class.

## 22. Verification ladder

A candidate passes the minimum prefix of this ladder required by its risk profile:

```text
1. schema/spec validation
2. architecture fitness
3. static/type/effect checks
4. unit tests
5. property/metamorphic tests
6. contract compatibility
7. state migration/replay validation
8. formal/model checks
9. deterministic simulation
10. fault/chaos tests
11. historical production replay
12. shadow execution
13. canary/progressive exposure
14. SLO/error-budget observation
15. independent evidence validation
16. atomic activation
```

Wall-clock sandbox duration alone is not sufficient. Evidence SHALL be based on coverage, sample size, scenario coverage, statistical power, or explicit deterministic proofs/checks as appropriate.

## 23. Assurance case

For R3/R4, activation SHOULD carry a structured claim-evidence graph.

```text
Claim: Generation G is safe enough for scope S
  Strategy: show invariant preservation
    Evidence: model-check result
    Evidence: property tests
  Strategy: show operational resilience
    Evidence: chaos suite
    Evidence: recovery SLO
  Strategy: show deployment safety
    Evidence: canary results
    Evidence: rollback test
```

The assurance case may be represented in GSN, CAE, or a simpler machine-readable DAG.

## 24. Evidence bundle

Each promoted generation SHOULD have:

```text
EvidenceBundle {
  generation_id,
  parent_ids,
  risk_class,
  claims[],
  evidence_artifacts[],
  evaluator_versions[],
  datasets_or_scenarios[],
  environment_hashes[],
  verification_results[],
  runtime_observations[],
  approvals[],
  provenance_root,
  signatures[]
}
```

Evidence artifacts SHOULD be content-addressed. R3/R4 evidence SHOULD be tamper-evident or signed.

## 25. Deployment and activation

The build artifact tested and approved MUST be the artifact activated.

Recommended rollout states:

```text
BUILT -> VERIFIED -> SHADOW -> CANARY -> ACTIVE
                       |         |
                       +-> REJECT
                                 |
                                 +-> ROLLBACK
```

Rollback SHALL reference a known generation, not attempt an ad-hoc reverse patch.

## 26. Recovery ladder

Prefer the smallest recovery scope.

```text
L0 retry pure/idempotent operation
L1 reset local resource
L2 restart component/plugin/actor
L3 reconstruct local state/projection
L4 restart process/service
L5 fail over runtime cell
L6 revert generation
L7 enter safe baseline mode
```

Escalation SHOULD be evidence-driven.

## 27. Cellular/distributed profile

For systems requiring blast-radius control, runtime cells SHOULD be independently fail-able and SHOULD avoid synchronous cross-cell dependencies on the critical path.

A cell may contain the full local execution stack but MUST obey global constitutional and evidence rules.

Traffic placement and cell membership belong to the control plane.

## 28. Plugin-runtime profile

A plugin-capable system SHOULD provide:

- typed provided/required services,
- explicit effect registration,
- scoped lifecycle,
- explicit capabilities,
- quiescence support,
- inverse or compensation hooks,
- generation/provenance identity,
- compatibility checks.

Plugin memory is non-authoritative unless explicitly designated otherwise.

## 29. Runtime-agentic profile gate

The mandatory Agentic Development Fabric in Section 11A is always enabled. This section governs agent/LLM behavior inside the shipped product at runtime and is disabled by default.

```yaml
profiles:
  agentic:
    enabled: false
```

Enabling it activates additional constraints. The universal kernel remains unchanged.

### 29.1 Agentic levels

#### AG0: Runtime disabled

No agent/LLM-specific runtime semantics. Development remains agent-native under Section 11A.

#### AG1: Agent runtime

Models/tools may execute, but persistent self-improvement is disabled.

Required additions:

- tool capability broker,
- model/tool execution journal,
- context provenance,
- agent sandbox appropriate to effects.

#### AG2: Persistent learning

The system may promote experiences into memory, skills, or heuristics.

Required additions:

- evidence-promotion firewall,
- source provenance,
- quarantine before persistent skill promotion,
- poisoning checks,
- rollbackable memory/skill versions.

#### AG3: Harness self-improvement

The system may generate new prompts, tools, workflow code, memory policies, or agent topology.

Required additions:

- immutable candidate generations,
- independent hidden evaluation,
- lineage/evolution DAG,
- complexity accountant,
- regularized mutation budget,
- OOD/transfer evaluation,
- agent cannot modify its active evaluator.

#### AG4: Bounded recursive self-improvement

The improvement mechanism itself may create candidate descendants of itself.

Required additions:

- maximum reflexive depth,
- independent evidence authority,
- evaluator epochs,
- metaproductivity tracking,
- replay-world/simulator evaluation where applicable,
- explicit compute/cost budget,
- no in-place self-overwrite,
- constitution and authority ceiling remain outside the recursive loop.

AG4 SHALL be treated at least as R4.

## 30. Agentic system state

When AG3+ is enabled, extend state with:

```text
A_t = (M_t, H_t, D_t, T_t, Imp_t)
```

where:

- M: model(s),
- H: harness/scaffold,
- D: data/evaluation/curriculum system,
- T: trainer/optimizer,
- Imp: mechanism that diagnoses, proposes, verifies, selects, and integrates improvements.

AG3 may modify M/H/D/T while Imp is fixed.
AG4 permits candidate descendants of Imp under the AG4 gate.

## 31. Agentic evolutionary lineage

Every AG3+ candidate is a generation node in an evolution DAG.

```text
EvolutionNode {
  generation_id,
  parents[],
  mutation_class,
  mutation_diff,
  diagnosis,
  claimed_mechanism,
  evaluation_vector,
  cost_vector,
  descendants[],
  evidence_root
}
```

The system SHOULD retain diverse stepping stones rather than only the current best candidate.

## 32. Agentic evaluation vector

Do not collapse improvement to one scalar where avoidable.

Recommended vector:

```text
F(g) = (
  immediate_utility,
  OOD_transfer,
  metaproductivity,
  learning_velocity,
  reliability,
  serving_cost,
  improvement_cost,
  complexity,
  safety,
  novelty_diversity
)
```

Safety floors remain constraints, not optimization rewards.

## 33. Metaproductivity

AG4 SHOULD measure whether a generation produces useful descendants, not only whether it performs well itself.

A simple proxy may aggregate:

- fraction of descendants that beat parent on held-out metrics,
- magnitude of descendant improvement,
- descendant OOD transfer,
- cost to discover improvements,
- diversity of productive descendants.

Metaproductivity MUST NOT replace current safety/reliability checks.

## 34. Agentic evaluator epochs

Within an evolution epoch, the evaluator version is immutable relative to the optimizer.

```text
Epoch e:
  optimizer may generate candidates
  evaluator E_e is fixed and inaccessible for mutation
```

Governance may later create `E_(e+1)` using independent review, fresh hidden probes, and backward comparison.

This allows evaluators to evolve without allowing self-grading.

## 35. Evidence-promotion firewall

AG2+ treats experiences as untrusted input and persistent skills as executable policy.

```text
experience
 -> candidate lesson
 -> quarantine
 -> corroboration
 -> regression/counterexample tests
 -> independent verification
 -> signed/versioned skill or memory artifact
```

Direct experience-to-skill write-through is forbidden for high-risk domains.

## 36. Agentic complexity accountant

AG3+ SHALL measure at least:

```text
prompt tokens
runtime tokens
latency
wall-clock
external tool calls
compute cost
number of tools/components
new dependencies
new capabilities
new failure modes where measurable
```

Periodic reverse ablation SHOULD remove mechanisms whose marginal value is not supported.

## 37. Harness metabolism

Stable expensive behavior MAY migrate toward cheaper layers:

```text
human procedure
 -> agent workflow
 -> persistent skill
 -> deterministic runtime primitive
 -> training data / model capability
```

Each downward migration MUST preserve provenance and pass the gate required by the destination layer.

## 38. Agentic reward-hacking defense

AG3+ MUST assume that candidate systems may exploit evaluation accidentally or strategically.

Therefore:

- critical metrics are recomputed outside candidate control,
- hidden evaluation data is not exposed to candidate code,
- candidate-generated result files are not authoritative evidence,
- independent mechanism checks SHOULD accompany outcome metrics,
- fresh/adversarial probes SHOULD be added over time,
- evaluator and evidence credentials MUST be inaccessible to candidates.

## 39. Reflexive depth and budget

AG4 MUST declare:

```yaml
recursive_improvement:
  max_depth: 2
  generation_budget: 32
  token_budget: 5000000
  compute_budget_usd: 250
  wall_clock_budget: 24h
```

Depth counts how many levels of improvement machinery are themselves being optimized.

Unbounded reflexive recursion is non-conforming.

## 40. Control flow for a generic change

```text
Observe
  -> Detect divergence/opportunity
  -> Diagnose smallest implicated component
  -> Create candidate generation
  -> Compute impact/dependency cone
  -> Determine risk/effect/coordination classes
  -> Run required verification ladder
  -> Build assurance/evidence bundle
  -> Stage/shadow/canary if required
  -> Independent activation decision
  -> Atomically switch active generation
  -> Observe SLO/invariants
  -> Accept or rollback
  -> Record outcome in control journal
```

## 41. Promotion algorithm

Pseudo-code:

```python
def may_activate(candidate, spec, evidence):
    risk = max(candidate.component_risk,
               candidate.effect_risk,
               candidate.mutation_risk)

    if not evidence.complete_for(risk):
        return DENY("missing evidence")

    if evidence.any_hard_invariant_failure():
        return DENY("constitutional violation")

    if candidate.requires_coordination() and not evidence.has_fence():
        return DENY("missing coordination/fencing")

    if candidate.expands_authority() and not spec.constitution.permits(candidate):
        return DENY("authority ceiling")

    if risk >= R3 and not evidence.independent_evaluation:
        return DENY("independent evaluation required")

    if candidate.profile == "runtime_agentic" and candidate.agentic_level >= AG3:
        if candidate.can_modify_active_evaluator:
            return DENY("self-evaluation authority")
        if not evidence.hidden_ood_pass:
            return DENY("transfer evidence required")

    return ALLOW
```

## 42. Conformance CLI contract

A future AAA engine SHOULD expose:

```text
aaa validate        # schema + hard invariant specification checks
aaa workplan        # compile dependency + conflict DAG for agent workcells
aaa workcell        # create/pin isolated workcell and capabilities
aaa lease           # inspect/acquire component/write-set leases
aaa graph           # component/authority/dependency/conflict graph
aaa swapcheck       # prove/check substitute compatibility for a component slot
aaa integrate       # compose immutable workcell outputs into a candidate generation
aaa impact          # smallest affected dependency cone
aaa verify          # execute risk-selected verification ladder
aaa evidence        # build evidence/assurance bundle
aaa build           # create immutable generation
aaa stage           # shadow/canary stage
aaa activate        # atomic active-generation switch
aaa rollback        # activate known-good ancestor
aaa stabilize       # execute declared recovery policy
aaa assess          # diagnostic architecture health vector
```

The CLI is not part of core semantics, but these operations define a useful executable interface.

## 43. Recommended repository layout

```text
/architecture
  aaa.yaml
  constitution.yaml
  capabilities.yaml
  risk-policy.yaml
  slots.yaml
  /contracts
  /development
    workcell-policy.yaml
    ownership.yaml
    integration-policy.yaml
    /task-graphs
  /feature-model
  /formal
  /evidence
  /profiles
    distributed.yaml
    adaptive.yaml
    incremental.yaml
    runtime-agentic.yaml

/components
  /<slot-id>
    /<implementation-id>

/src
  /domain
  /ports
  /adapters
  /runtime
  /composition-root

/tests
  /unit
  /property
  /contract
  /architecture
  /swap
  /replay
  /chaos

/generations
  manifests only or references to artifact store

/.workcells
  ephemeral isolated worktrees/sandboxes; never authoritative
```

Development-agent metadata is universal. Runtime-agent implementation directories SHOULD exist only when the runtime-agentic profile is enabled.

## 44. Minimal adoption profile

A small ordinary application can conform without becoming infrastructure-heavy.

Minimum:

1. constitution with a few hard invariants,
2. mandatory Agentic Development Fabric with isolated workcells and no shared mutable workspace,
3. component slots plus versioned contracts for replaceable boundaries,
4. domain/adapter boundary,
5. typed effects for external/state mutations,
6. immutable build/version identity,
7. rollback path,
8. architecture, contract, and swap-compatibility tests,
9. control journal for deployments and incidents,
10. explicit risk classification.

Everything else is activated by need.

## 45. Migration from AAA v2-v6

### Replace

- universal 5-layer resilience chain -> operation-specific resilience contracts,
- mandatory event sourcing -> pluggable state strategy,
- fixed evaluator forever -> evaluator epochs with external governance,
- 7-day sandbox -> evidence/coverage/power-based verification,
- one score -> hard gates plus diagnostic vectors,
- one optimization cell -> runtime cells plus evolution lineages,
- mutable deployments -> immutable generations,
- runtime-agent-first architecture -> universal kernel plus mandatory agentic development fabric and gated runtime-agentic profile.

### Preserve

- hexagonal domain isolation,
- externalized evaluation,
- bounded optimization,
- progressive rollout,
- replay where semantically appropriate,
- cellular blast-radius control,
- causal/evidence DAGs,
- reversible composition,
- formal verification for high-risk invariants.

## 46. Research-derived implementation map

The specification intentionally borrows mechanisms rather than frameworks wholesale.

- seL4: minimal privileged kernel and capability isolation.
- Buck2/DICE/Bazel-style execution graphs: isolated incremental work units, explicit dependencies, reproducible composition.
- Software product lines/component models: logical variation points and implementation binding.
- Object-capability systems, OPA, Cedar: least authority and explicit policy.
- DeepSeek Harness/Cordis: lifecycle-scoped, reversible composition.
- Nix/Guix: immutable generations and rollback by pointer change.
- Temporal/Restate/DBOS: durable execution and replayable workflows.
- Complete CALM, CRDTs, I-confluence: monotonicity-driven coordination decisions.
- Buck2/DICE, Salsa, Differential Dataflow: dependency-aware minimal recomputation.
- Rainbow, Models@run.time: causal runtime reflection models.
- Dynamic Software Product Lines: explicit runtime variability and valid-configuration spaces.
- Simplex/runtime assurance: advanced controller plus independent baseline/fallback.
- Self-stabilization: legitimate-state convergence and closure.
- Assurance cases/GSN/CAE: structured claim-evidence promotion.
- Argo Rollouts/Flagger: progressive activation and rollback.
- Chaos Mesh/Toxiproxy/Stateright/Quint: adversarial and formal validation.
- Sigstore/in-toto: signed provenance and evidence lineage.
- DGM/HGM/AIDE2/VERSE/RRSI/Dream-RSI: bounded recursive improvement, lineage search, metaproductivity, verification, regularization, and replay-world meta-optimization.

## 47. Non-goals

AAA v7.1 does not require:

- microservices,
- distributed deployment,
- event sourcing,
- LLMs in the shipped runtime,
- self-modifying code,
- autonomous optimization,
- Kubernetes,
- a graph database,
- blockchain,
- formal proofs for ordinary low-risk code.

It provides gates for those capabilities where useful.

## 48. Summary invariant

The architecture may evolve rapidly, but authority, evidence, state transitions, development ownership, and integration remain explicit. Independent agent fleets may work aggressively in parallel because they never share mutable development authority; they meet only through versioned contracts and integration transactions.

The core rule is:

> No component may silently widen its authority, rewrite the evidence used to judge itself, or mutate the currently judging generation in place. Every meaningful adaptation is attributable, bounded, and reversible or compensated according to its effect semantics.

