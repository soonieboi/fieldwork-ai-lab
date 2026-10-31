# Agent-contract-v1 — scoped workflow evaluation plan

Written before implementation. This is an authored deterministic contract/task
fixture suite, not a test of live-model competence, factual support, or security
in general. No human/model semantic judge or paid inference is used.

## Unit, corpus and provenance

The unit is one question, frozen synthetic shop corpus, scripted endpoint
trajectory, run budget and optional cancellation/error event. Freeze exact case
IDs, response JSON, expected terminal state, allowed tool sequence/counter bounds,
and corpus hashes before implementing the runner. The shop policy is invented;
no real customer, merchant, purchase or private document is represented.

These are public author-known regression cases. There is no train/test split or
out-of-distribution claim for scripted contract fixtures. Real model selection or
policy tuning needs a separately designed development/held-out evaluation with
new independent samples. Do not relabel a script passing as agent task quality.

## Measurements and slices

Report the number of scripted cases exercised and expected outcomes matched,
with per-case status/tool/budget observations. Separate slices:

- Valid choice trajectories: search/read/finish, refinement, intentional abstain.
- Runtime authority: forbidden tool, guessed/undiscovered source, invalid arguments,
  finish without read evidence, invalid citations, and altered provenance.
- Lifecycle: step/time/output-reservation exhaustion, cancellation before request,
  after response and before tool execution, refusal and malformed/provider errors.
- Transport/configuration: reuse reviewed fake-server coverage, no dispatch in
  disabled/insufficient mode, no credential borrowing, bounded context and jobs.

Completion is only a terminal finish whose structured claims and read-source IDs
pass the local contract. A citation-valid but false claim can still complete:
include this negative-control example and label semantic support NOT ASSESSED.
Cancellation passes only when no later request/tool executes after acknowledgment;
request abort alone is not a cancel-success oracle. Count every attempted model
request and reserve output-token caps before dispatch, including failed calls.
Missing reported usage is unknown, never zero or an estimated measurement.

Assertions use actual runtime action dispatch logs, authoritative source IDs,
terminal states, request counts and numeric limits. Do not award success for
keywords/citation presence, a model's self-report of safety, or a claimed “done.”
No aggregate score combines these with frozen RAG or serving metrics.

## Review and reproducibility

Manifest hashes and exact fixture inventory must be validated before use.
Contract fixtures and expected results must be inspectable. Tests should mutate
invalid schemas/IDs and use controlled clocks/events for deterministic boundary
checks. Local fake-server tests verify that runtime choices actually drive HTTP
round trips and safe tools, rather than bypassing dispatch with a canned result.
No fixture output is presented as a live-model answer in the frontend.

Keep evals/v1, evals/reports/v1-*, lexical gate/core/scorer and the generation
contract fixtures unchanged. Reproduce those prior artifacts in CI. A future
live-agent study must separately evaluate task coverage, per-claim support,
appropriate refusals, tool violations and cost/time with real authorized samples,
reviewer provenance, denominators, uncertainty and failure examples.
