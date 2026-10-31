# Fieldwork — AI Engineering Lab

A runnable starter inspired by three AI engineering concepts: bounded agents,
retrieval augmented generation, and vLLM serving metrics. This is a new local
project, not a reproduction of an existing codebase or screenshot layout.

## Start in under a minute

Requires Python 3.10 or newer. No packages, API keys, network calls, GPU, or model
downloads are needed for offline mode.

```sh
cd ai-engineering-lab
python3 -m lab serve
```

Open **http://127.0.0.1:8080**. Stop with Ctrl-C. Choose another port with
`python3 -m lab serve --port 8081`. Use the `127.0.0.1` URL for browser API calls.

The dashboard's **Docs** tab includes quickstart commands, workflow architecture,
simulated versus real behavior, optional model-serving setup, metric definitions,
and troubleshooting. Each demo links to relevant help. Documentation sections
have shareable local routes such as `http://127.0.0.1:8080/#docs/models`;
these links work only while a lab is running on the viewer's own machine.
Use the Docs links or the top tabs to return to demos without clearing results.
The top tabs support Left/Right arrows and Home/End keys.

The first browser example is an **invented shoe-shop returns policy**: “I bought
a pair of shoes 10 days ago and haven't worn them. Can I return them?” The policy
still requires a receipt; that detail must not be assumed. The contrasting bicycle
helmet question asks about an unmentioned item. This is not a real merchant's
policy or a real purchase. Choose the lab documents to explore the technical corpus.
These examples live in `examples/shop/`, separately from the frozen v1 eval corpus.

## What works

- **Retrieval:** loads the four bundled Markdown documents, creates overlapping
  85-word chunks, embeds them as normalized sparse TF-IDF vectors, and ranks by
  cosine similarity. Answers are quoted source passages with stable chunk IDs.
  A development-calibrated lexical gate can abstain even when search finds
  similar passages. It is not semantic sufficiency or confidence calibration;
  it can refuse supported questions and accept unsupported/conflicting ones.
  Diagnostic retrieval is separate from answer sources. No neural model.
- **Optional cited generation:** an explicitly configured chat-completions endpoint
  can return short claims citing supplied passages. Strict JSON/citation checks
  reject invalid or incomplete responses; valid citations do not establish factual
  support. Offline mode remains the default. Only fake HTTP endpoints were tested;
  no live model quality or prompt-injection protection is claimed.
- **Agents:** a deterministic planner → researcher → reviewer → finish loop,
  with selectable tasks and a 1–6 step budget. Roles execute sequentially.
  Only corpus search and term-coverage checks are available. No shell, network,
  file writes, autonomous migration, or real LLM reasoning.
- **Bounded structured-choice agent:** a separate everyday walkthrough quotes the
  invented shop policy. Its optional endpoint mode lets a model choose search,
  read, finish or abstain. Runtime tool permissions, discovered-source IDs,
  step/time/requested-output caps, cancellation and bounded local jobs are enforced.
  Completion means a workflow contract, not verified factual or live-agent quality.
  The original deterministic agent remains unchanged.
- **Serving:** synthetic local stream replay plus a real OpenAI-compatible SSE
  adapter for an endpoint you explicitly choose. Replay results reflect fixture
  delays, never model performance. The real adapter measures TTFT, mean interval
  between nonempty content events, duration, and server-reported completion
  tokens per total request second. Missing token usage stays unavailable.
- **Evaluation:** a versioned 50-case authored synthetic documentation-QA suite,
  with 30 development and 20 held-out cases scored separately. It compares raw
  extraction and a lexical gate using exact evidence spans, retrieval metrics,
  decision confusion counts, abstention, provenance, and slice denominators.
  It does not judge semantic factuality or LLM outputs. The four-question legacy
  document-hit smoke check is retained and explicitly labeled as such.

## CLI

```sh
python3 -m lab ask 'How do bounded agents restrict tools?'
python3 -m lab agent --task safety --budget 6
python3 -m lab agent --task retrieval --budget 3
python3 -m lab evaluate
python3 scripts/check_evaluation.py
python3 scripts/check_generation_contract.py
python3 scripts/check_agent_contract.py
python3 -m lab eval-suite --split development --output results/development.json
python3 -m lab eval-suite --split heldout --output results/heldout.json
python3 -m lab replay
python3 -m unittest discover -s tests -v
```

CLI output is JSON. A budget of three stops after review and returns
`budget_exhausted` without a final answer. Unknown tasks and invalid budgets
are rejected. Core logic is in `lab/core.py`, HTTP routes in `lab/server.py`,
and the responsive dashboard in `web/index.html`.

Read the pre-implementation [evaluation design](docs/evaluation-design.md) and
[baseline results](docs/evaluation-results.md) before interpreting scores. The
policy was frozen using development cases only, before held-out scoring. The
public held-out split is author-known and shares underlying facts with development;
it is not an independently blind generalization test. No held-out threshold
tuning is performed. Future iterations must treat these cases as exposed data.

## Optional cited-answer configuration

Generation is separate from the serving benchmark. Nothing calls an endpoint until
you explicitly enable generation and request an answer. Provision a compatible
server yourself; no model or dependencies are downloaded by this project.

```sh
export LAB_GENERATION_ENABLED=1
export LAB_GENERATION_BASE_URL=http://127.0.0.1:8000/v1
export LAB_GENERATION_MODEL=YOUR_SERVED_MODEL
export LAB_GENERATION_FORMAT=json_schema
python3 -m lab serve --port 8081
```

Open the matching localhost URL, choose **Endpoint (optional)**, and submit a
question; or use the CLI with the same environment:

```sh
python3 -m lab generate "I bought a pair of shoes 10 days ago and haven't worn them. Can I return them?" --corpus shop
```

Your question and retrieved excerpts are sent to the configured endpoint. Use only
an authorized destination and data. No live provider calls or private documents
were used to develop this adapter. For authentication, supply
`LAB_GENERATION_API_KEY` through your private environment/secret manager. It does
not inherit benchmark `LAB_API_KEY`. No keys or endpoint configuration go into
the browser. `.env.example` has safe placeholders only; no env file is auto-loaded.

HTTPS is required outside literal loopback IPs or `localhost`. Redirects/proxy
inheritance are disabled; TLS verification stays enabled. Timeout defaults to
10 seconds (1–30 allowed), with bounded request/context/response sizes. Connected
requests are interrupted at the deadline; OS-managed DNS can exceed it. At most
two browser generation requests run concurrently. There is no auto-retry or
automatic paid-usage budget. Keep this unauthenticated development server local.

Providers differ. `LAB_GENERATION_FORMAT=json_schema` requests strict structured
output. Explicitly select `json_object` only for a server supporting JSON mode;
local schema/citation checks still run. No silent downgrade occurs. Choose
`LAB_GENERATION_TOKEN_FIELD=max_completion_tokens` if required by your server;
the default is `max_tokens`. `LAB_GENERATION_MAX_TOKENS` defaults to 512 (1–1024).
Unsupported features, refusals, invalid citations, and partial output are handled
without displaying an unchecked partial answer or provider error bodies.

Read the [pre-code design](docs/cited-generation-design.md) and the
[separate generated-support review rubric](docs/generated-support-review.md).
The 19 authored generation contract cases include a citation-valid but false
claim: protocol validity is intentionally not presented as semantic correctness.
Frozen v1 scores/reports are unchanged; generated paraphrases are never scored
with extractive token offsets. Real-model quality remains unverified.

## Bounded agent walkthrough and optional model choices

In the Agents tab, the default offline walkthrough uses scripted actions and
quotes a read paragraph. It makes no endpoint request. The optional model mode
chooses one schema-validated action per turn; only in-memory `search_documents`
and `read_source` can execute. Read accepts only a source discovered in that run.
No shell, arbitrary path, file write, network tool or new tool permission exists.

```sh
python3 -m lab agent-run "I bought a pair of shoes 10 days ago and haven't worn them. Can I return them?" --mode offline --corpus shop
```

The original `python3 -m lab agent --task safety` fixture is still available.
For model-driven choices, separately configure `LAB_AGENT_ENABLED=1`,
`LAB_AGENT_BASE_URL`, `LAB_AGENT_MODEL`, and (if needed) `LAB_AGENT_API_KEY` privately.
No generation or benchmark key is borrowed. The `LAB_AGENT_FORMAT`, `TIMEOUT`,
`MAX_TOKENS` and `TOKEN_FIELD` settings use the same reviewed transport/capability
rules as generation. Choose `--mode endpoint` only with an authorized destination
and data; requests include the question and accumulated tool observations.

Defaults are 6 choices, 15 seconds, and 1536 cumulative requested completion-token
caps. Use `--max-steps` (1–8), `--seconds` (2–30), and `--output-budget` (1–2048)
to choose smaller bounded runs. Per-choice output cap defaults to 256. Caps are
reserved before requests and not refunded on failure; they are not measured
model tokens or a guaranteed billing limit. Missing reported usage stays unknown.
Input/context is byte bounded, not counted with an assumed tokenizer.

Stop run requests server-side cancellation and waits for acknowledgment after any
current bounded request. It does not merely abort fetch. CLI Ctrl-C interrupts
the local run. There are at most two active and eight retained local jobs, no
unbounded queue or persistent job files, and no multi-user authentication. Keep
the development server on loopback. DNS can outlast network deadlines.

The [pre-code design](docs/bounded-agent-design.md) and
[scoped workflow evaluation](docs/agent-evaluation-v1.md) distinguish runtime
contracts from factual/task quality. The 23 frozen authored workflows include
forbidden tools, undiscovered IDs, budgets, cancellation, errors, and a
citation-valid false claim. Fake HTTP round trips verify dynamic choices drive
actual safe-tool dispatch. No live-agent competence or general injection safety
is claimed, and frozen v1 RAG plus generation contract artifacts remain unchanged.

## Optional real endpoint / vLLM

Provision vLLM and model weights separately on suitable hardware. This project
does not install or start a model server. Supply the API root (including `/v1`)
and the exact model name configured by your server:

```sh
python3 -m lab benchmark \
  --base-url http://127.0.0.1:8000/v1 \
  --model YOUR_SERVED_MODEL --runs 3 --timeout 30
```

For authenticated endpoints set `LAB_API_KEY` in the terminal environment through
your normal secret management flow. Credentials are not logged or accepted by
the web UI. Remote endpoints receive only this fixed public prompt:
“Explain retrieval augmented generation in three short sentences.”
The corpus and user questions are never sent by this adapter. HTTP is suitable
for local endpoints; use HTTPS for remote authenticated endpoints. Redirects
are refused so credentials are not forwarded to a different location.

The request uses streamed chat completions with `stream_options.include_usage`.
Some compatible servers do not support that option and will return an error;
failures are recorded by exception type, without response bodies or secrets.
The command exits nonzero if any run fails. Maximum 10 sequential requests;
each response is size-limited. Timeout is applied to socket operations and
checked between lines: a blocking read can extend the total deadline by up to
one socket timeout. No automatic retries or warmup; the first run is included.

TTFT begins before opening the HTTP request and ends at the first nonempty
content delta. Streaming deltas may contain several tokens, so event spacing is
**not token-level ITL**. Completion tokens per second uses the whole response
duration; it is **not post-prefill decode speed or aggregate server throughput**.
No real-model benchmark results are bundled. Real GPU performance remains
unverified until you run against your own server.

## Extend it

Add UTF-8 Markdown documents to `corpus/`, then restart the server or rerun the
CLI to rebuild the index. Chunk IDs depend on word offsets and may change when
documents change. TF-IDF is lexical: synonyms and paraphrases can miss evidence.
For a real RAG pipeline add a separate embedding/generation adapter and evaluate
retrieval and answer quality independently. Document text remains data, never
executable instructions.

The HTTP app is a local development tool: it binds loopback, rejects cross-origin
POST requests, requires small JSON requests, and offers no upload or arbitrary
network endpoint feature. Do not expose it on a public interface.

## Verification and reference access

See `VERIFICATION.md` for the recorded checks. Screenshot materialization failed
twice in the execution environment, so implementation follows the extracted
functional brief rather than pixel-level details. The app has no external fonts,
scripts, telemetry, or runtime dependency fetches.
