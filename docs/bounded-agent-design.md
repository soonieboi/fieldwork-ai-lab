# Bounded model-driven documentation agent — PR #3 design

Written before implementation. Base: merged PR #2 at
`27875cc733ce9f2a4cd48ac489ca5c7bdcf41642`; post-merge CI `41163223662` passed on
Python 3.10/3.14. This PR does not change frozen RAG-v1 artifacts, the original
deterministic `run_agent`, cited-generation contracts, or serving benchmarks.

## Intended task and modes

An assistant checks the invented shoe-shop documents to help with: “I bought a
pair of shoes 10 days ago and haven't worn them. Can I return them?” The receipt
condition remains unresolved by the question and must not be invented. Other
merchandise absent from the documents should not receive invented rules.

The existing technical plan/search/check/finish fixture remains available.
A new offline walkthrough uses scripted choices and quotes a read paragraph;
it is clearly labeled as no model inference. The optional endpoint mode uses a
model's structured choices at every step; it is not a renamed fixed sequence.
A model can search/refine, read, finish, or abstain. No live model calls, model
downloads, new credentials, paid calls, private data or deployments are performed
in this implementation or its tests.

## Safe actions and runtime authority

Exactly four action names are recognized: search_documents, read_source, finish,
and abstain. Only the first two execute tools. Runtime dispatch independently
enforces the allowlist, action-specific argument types/bounds, and permissions;
a prompt/schema alone is not the security boundary. There is no shell, arbitrary
path, filesystem write, browser/network tool, infrastructure operation, or dynamic
function lookup. Endpoint traffic is fixed by operator environment configuration.

Search operates on the selected in-memory Index and returns at most three source
IDs, scores and short snippets. Read accepts only an exact ID previously discovered
by this run and returns its original paragraph. Unknown/undiscovered IDs are
rejected; model-provided paths are never opened. Read provenance is checked against
that Index. Finish requires at least one read source and exact citations drawn
only from read evidence, using the cited-claim validator. Citation/provenance
validity is not factual support. Completed means workflow contract completion,
not verified task correctness or resistance to prompt injection.

The unchanged lexical gate checks the original question before endpoint dispatch
and again against read evidence before finish. It is conservative and fallible,
not a semantic judge. Retrieved documents and questions stay untrusted prompt
data; no chain of thought is requested, exposed, or treated as authorization.
Malformed, forbidden, inconsistent, truncated, or uncited model actions stop the
run without executing the proposed tool or showing a partial final answer.

## Versioned action schema

Every response has exactly schema_version=1, action, query, source_id, claims,
and reason. Search requires only a nonempty bounded query; read requires only
a discovered source_id; finish carries 1–6 bounded cited claims; abstain has a
nonempty bounded reason and no claims. Inactive fields must be empty. Strict
JSON duplicate-key/type/property checks apply. json_schema/json_object capability
selection is explicit, with the same local validation and no silent fallback.
Provider refusals and protocol/transport errors are terminal, not tool actions.

## Budgets, interruption and traces

Maximum steps is 1–8 model choices, default 6. One choice can execute at most one
read-only tool; finish/abstain also consume a step. Maximum elapsed budget is
2–30 seconds, default 15; transport timeouts are clipped to remaining time, with
no new request when less than one supported timeout second remains. Each stage
checks time and cancellation before further model/tool activity. OS-managed DNS
can outlast the network deadline, as documented by the transport.

Cumulative requested completion-token caps are reserved BEFORE dispatch and never
refunded, even on failures. Default allowance is 1536, allowed 1–2048; per-call
cap defaults to 256 and is clipped to remaining allowance. This bounds requested
output, not actual provider billing. Input/context are byte-bounded, not counted
with an assumed tokenizer. Server-reported completion usage is recorded only
when valid; missing usage stays unknown, and a reported cap violation stops
before tool execution. Never label reservations as measured model tokens.

Cancellation is cooperative: check before/after each bounded endpoint request
and immediately before tools. An in-flight provider call may take its remaining
timeout to return; after cancellation no new model call/tool starts. CLI Ctrl-C
closes the current transport and returns cancellation. Browser cancellation must
request server-side cancellation and wait for acknowledgment, not merely abort
fetch and allow the run to continue silently.

Trace only explicit requests/actions, tool outcomes, source IDs, terminal status,
step counts, elapsed time and budget accounting. Do not expose hidden reasoning,
raw provider errors, credentials, or endpoint configuration. Trace/model text is
plain text in the browser. Offline fixture pacing and token allowances are not
inference/serving metrics.

## Operator configuration and local jobs

Separate LAB_AGENT_ENABLED=1, BASE_URL, MODEL, API_KEY, FORMAT, TIMEOUT,
MAX_TOKENS and TOKEN_FIELD settings (all prefixed LAB_AGENT_) are required for
endpoint mode. No silent reuse of generation/benchmark credentials. Reuse the
reviewed direct HTTPS/loopback transport and framing/size/deadline validation.
The browser can choose a corpus and bounded run parameters, never a URL, model,
credential, callable, or new tool permission.

Keep at most two active local jobs and eight retained jobs. Evict completed jobs
when capacity is needed; no unbounded queue or file persistence. IDs are opaque
local job identifiers, not a claim of authentication. Start/cancel and job reads
require exact local Origin/Host. The loopback development server is not public
hosting or multi-user isolation. Offline mode requires no credentials or network.

## Evaluation boundary before implementation

See `docs/agent-evaluation-v1.md` and the frozen authored agent-contract-v1
fixtures. Assess explicit workflow contracts/tool restrictions/budget enforcement,
not semantic agent quality. Use scripted responses and local fake HTTP endpoints.
Keep RAG retrieval scores, generated-support review, agent workflow checks and
serving measurements separate; no combined “AI quality” score.

Independent review and browser QA precede merging PR #3. Existing previews stay
on 8080/8091; this checkout must not use CritterDex 4317. Any new preview port
must be checked before use and clearly identified as unmerged code.
