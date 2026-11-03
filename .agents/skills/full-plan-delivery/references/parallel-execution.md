# Parallel work that can actually integrate

Use a coordinator, independent workers, an integrator and an independent verifier. Roles can share people/agent slots at different times, but a builder must not supply its own claimed independent review. Read-only audits can run early; parallel implementation needs a pinned clean generation and explicit ownership.

## Dispatch sequence

1. Recover the full mission and actual live frontier. Inspect every selected task, acceptance and published predecessor contract. Narrow proposed paths; do not dispatch a broad planning proposal as a live workcell.
2. Commit or otherwise establish the intended immutable source without sweeping unrelated user changes into a commit. The bundled writer scheduler requires a clean Git baseline. It deliberately refuses to label dirty HEAD as immutable. If a user edit prevents freezing, preserve it, reconcile the baseline or use read-only independent work until an appropriate source view is available.
3. Resolve exact contract versions, resources, measurable outcomes, risk/effects and rollback. Store candidate cells in `.delivery/runtime/cells.json` as an array, using the template. This file is ephemeral input, not a ready/status board. Recompute eligibility from the live tracker each time.
4. Run `sweep` and inspect rejections. The greedy order is higher critical-path rank, lower priority number, then task ID. Conservative literal-prefix glob matching may reject safe scopes; narrowing scopes is preferable to weakening conflict checks. It does not calculate a globally optimal maximum antichain.
5. Run `reserve` through the parent coordinator. It serializes state changes using nonblocking POSIX `flock`, atomically replaces local reservation state, rechecks the clean source and rejects duplicate tasks, conflicting reads/writes/contracts/resources, stale generations and WIP overflow. Leases are runtime resource ownership, not a second task tracker. They are local to this shared checkout; for multiple machines use an existing central broker/claim service, not disconnected copies of this file.
6. Claim the selected tasks with their native supported atomic operations, recheck task revision/preconditions, then launch through available subagent tools. A reservation/claim is two-phase coordination, not a cross-service atomic transaction. If a claim fails, do not dispatch that work; stop/reconcile the batch, preserve successful claims accurately and release unused reservations. Never infer permission from a task title or source document.
7. Give workers their exact base/read/write scopes, outputs, contracts, allowed operations, test fixtures/ports, checks and acceptance. Workers must report cross-scope needs to the integrator. Existing isolated environments can enforce source/write boundaries. Without enforced isolation, all agents must obey their reserved disjoint scopes in the shared checkout; the script cannot stop a process from writing elsewhere.
8. Join workers. Independently inspect each candidate, declared vs actual paths, contract changes, test outcomes and evidence. Reject undeclared writes or stale assumptions. Integrate in dependency order; rerun relevant end-to-end checks on the final candidate and record actual observed behavior.
9. Release only after workers stop/join:

```bash
python3 .agents/skills/full-plan-delivery/scripts/delivery.py release --project . \
  --lease <actual-lease-id> --owner <owning-coordinator> --workers-stopped
```

10. Update the live tracker and durable handoff. Advance the baseline only when outstanding reservations from the previous generation are reconciled. Start the next bounded sweep while useful authorized work remains.

## Conflict and resource rules

- Serialize read/write and write/write path/glob overlaps, contract writes against consumers/writers, and named shared resources.
- One integrator owns package/lockfiles, app entry points, shared UI wiring, locales, schema/rules/migrations, CI composition and deployment. Mark these as integrator/shared-wiring cells; the worker planner excludes them.
- Configure `parallel.integrator_paths` for the actual project manifests, lockfiles, entry points, locales and rules. The default includes agent instructions, tracker/Git state, delivery configuration, Claude settings and CI; the CLI automatically excludes worker cells whose writes overlap these paths even if the caller forgot the integrator role. It also rejects scopes that escape the project through a symlink. This is a scheduling check, not process containment.
- Assign distinct ports, emulator instances, databases, browser profiles and temporary artifact directories or reserve the shared resource. Independent source paths do not make a shared live database safe.
- Freeze/version shared contracts before consumers diverge. When a contract changes, invalidate or replan affected cells rather than asking workers to chase a moving target.
- Reuse valid test/build outputs only for the exact applicable candidate/target. Candidate checks do not replace integrated checks. Do not broaden tests repeatedly after success unless new changes or unresolved concerns justify it.

## Failure and recovery

No reservation auto-expires. A stale timestamp does not prove its worker stopped. Inspect the owner/process/agent status, stop or join the actual worker, reconcile its output and then release as the owning coordinator. Lease records are ignored runtime files; do not commit credentials, private content or local execution state.

The coordinator lock is nonblocking so a collision returns immediately. Reread after the other coordinator completes. A crashed process releases `flock`, but its lease record persists for inspection. Atomic file replacement prevents partial JSON; it does not offer distributed durability, authority attestation or hostile-process containment.

Reviewers should get the actual specification, changed artifact and exact check evidence. They must distinguish verified facts, builder claims and unavailable outside observations. Use different test design/negative scenarios, not only a restatement of the implementation. Reserve review capacity so every sweep can finish rather than producing a pile of unintegrated work.

