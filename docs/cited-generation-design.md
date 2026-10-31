# Optional cited generation — contract v1 (PR #2)

This design precedes implementation. Base: merged PR #1 at
`6e8256ead29bd42bd4966a597741b48f4ad6bc1e`, whose post-merge Python 3.10/3.14
checks passed. This PR adds only an optional cited-answer adapter and its contract
checks. Agents, serving benchmarks, retrieval ranking, the frozen v1 evaluation,
its labels/policy/splits/reports, and default offline operation stay unchanged.

## Operation and authorization boundary

Offline extraction remains the default and never calls a provider. A separate
CLI command and an optional browser choice can request a generated response only
when an operator explicitly enables and configures the adapter in the server/CLI
environment. No endpoint, model setting, or credential is accepted from a browser
request. There is no browser credential form and no automatic endpoint discovery.

Environment configuration: LAB_GENERATION_ENABLED=1, LAB_GENERATION_BASE_URL,
LAB_GENERATION_MODEL, optional LAB_GENERATION_API_KEY, LAB_GENERATION_FORMAT
(json_schema by default, or explicit json_object), LAB_GENERATION_TIMEOUT
(default 10 seconds, permitted 1–30), LAB_GENERATION_MAX_TOKENS (default 512,
permitted 1–1024), and LAB_GENERATION_TOKEN_FIELD (max_tokens by default or an
explicit max_completion_tokens). The generation key does not silently fall back
to the benchmark key. Example configuration contains placeholders/empty secrets.
No credentials are acquired, printed, logged, saved, or committed by this task.

Only deterministic fake HTTP endpoints on loopback are exercised during this PR.
No live inference, model download, private-data transmission, deployment, or paid
call is authorized or performed. A user who later enables an endpoint must choose
a destination they are authorized to use and approve sending their question and
retrieved passages there. The UI describes this transmission before the action.

## Retrieval and refusal boundary

Use the unchanged Index.answer lexical gate from PR #1 before provider dispatch.
If the gate abstains, return a clear local abstention with no provider call and no
generated claims. This is not a semantic support check: it can reject supported
questions or accept unsupported/ambiguous/conflicting questions. A model may
also abstain, and no returned answer is labeled factually verified.

Pass at most three original retrieved chunks with their authoritative IDs and
source provenance. Reject oversized context/request payloads rather than silently
truncating evidence. Prompt the model to treat quoted documents and the question
as untrusted data, ignore embedded instructions, cite only the provided IDs, and
abstain when support is insufficient or conflicting. No tools or execution
capabilities are offered. Prompting and citation validation do not establish
prompt-injection protection or semantic support.

## Versioned response contract and local validation

The generated JSON object has exactly schema_version (integer 1), status
(answer or abstain), reason (string), and claims (array). Each claim has exactly
text (nonempty bounded plain text) and citations (nonempty unique array of IDs).
An answer contains 1–6 claims; an abstention contains no claims and has a reason.
Every citation must exactly match a supplied evidence ID. At most three citations
per claim and bounded total text/reason lengths limit output. Unknown properties,
duplicate JSON keys, invalid types (including bool-as-int), nonfinite JSON
numbers, missing/unknown/duplicate citations, malformed/oversized bodies, and
inconsistent statuses are rejected. Provider refusals and non-stop/truncated
completions never become a partial answer. No repair or retry is automatic.

The adapter requests Chat Completions without streaming. json_schema uses a strict
schema whose citation enum is generated from the actual allowed IDs. json_object
must be selected explicitly for a server supporting only JSON mode. Both paths
undergo the same local validation; a valid JSON object is not automatically a
valid answer. Do not assume a model supports a response format, token-limit
parameter, or refusal behavior from its name. Unsupported capabilities produce
a clear error; no silent downgrade or unstructured-text fallback occurs.

For an accepted response report citation-ID validity and exact source-chunk
provenance separately from semantic_support=not_assessed. Valid citations merely
point at available passages; they do not prove a claim is true or entailed.
Render model text as plain text, never HTML. Do not describe an endpoint response
as verified live-model quality; test endpoints can emit deterministic fixtures.

## Transport and local server boundaries

Require HTTPS for every non-loopback endpoint, including unauthenticated ones.
HTTP is permitted only for literal loopback IPs or localhost. Reject credentials,
queries/fragments, backslashes/control characters, and invalid ports in endpoint
URLs. Do not follow redirects or inherit proxy configuration. Preserve standard
HTTPS certificate verification. Keep credentials out of exceptions and public
status. Authentication/configuration errors and provider bodies are not echoed.

Use finite socket timeouts, a monotonic deadline checked between operations,
a bounded response body, a bounded request/context, and a finite output-token
request. DNS resolution is OS-managed; no hard wall-clock guarantee is claimed.
No automatic retry. Limit concurrent generation requests. A browser generation
request must have the exact local Origin and Host, and only a question field;
existing offline routes remain compatible. These checks are not user
authentication. The stdlib development server remains loopback-only, unsuitable
for public hosting, and does not claim multi-user isolation or a spend budget.

## Testing and evaluation scope

Keep evals/v1, evals/reports/v1-*, lab/core.py, lab/abstention.py and its policy,
and lab/evaluation.py unchanged. Run the existing frozen report reproduction
checks to prove preservation. Generated paraphrases must never be scored with
extractive word-offset/token-precision rules.

Add a separately versioned, authored contract fixture suite. It exercises valid
schema/citations, refusal, missing evidence/no dispatch, malformed/duplicate JSON,
unknown/missing citations, extra properties, content and request bounds, timeouts,
redirect/error handling, origin/configuration restrictions, and rendered modes.
Use a local fake server plus isolated unit tests for HTTPS/header behavior. Label
all fixture outputs deterministic and not model inference. A successful fixture
is a protocol/validation result, not answer-quality evidence.

A separate support-review rubric for future authorized real samples must record
question, corpus snapshot, retrieved IDs, model/configuration, claim text and
citations, and a reviewer judgment for each claim: supported, contradicted,
insufficient evidence, or not assessable, with rationale/evidence. Also review
coverage, appropriate abstention, and malicious-instruction handling. No judge
or quality score is fabricated now. Preserve denominators, sampling policy,
reviewer provenance, and disagreements when such a study is actually conducted.

## References checked

The official Chat Completions reference documents response_format differences and
model-dependent parameter support. The Structured Outputs guide distinguishes
schema adherence from factual mistakes and documents refusal handling. These
references inform the wire contract, not an assumption that any compatible
server implements every feature:

- https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- https://developers.openai.com/api/docs/guides/structured-outputs
