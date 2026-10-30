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

## What works

- **Retrieval:** loads the four bundled Markdown documents, creates overlapping
  85-word chunks, embeds them as normalized sparse TF-IDF vectors, and ranks by
  cosine similarity. Answers are quoted source passages with stable chunk IDs.
  A development-calibrated lexical gate can abstain even when search finds
  similar passages. It is not semantic sufficiency or confidence calibration;
  it can refuse supported questions and accept unsupported/conflicting ones.
  Diagnostic retrieval is separate from answer sources. No neural model.
- **Agents:** a deterministic planner → researcher → reviewer → finish loop,
  with selectable tasks and a 1–6 step budget. Roles execute sequentially.
  Only corpus search and term-coverage checks are available. No shell, network,
  file writes, autonomous migration, or real LLM reasoning.
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
