# Verification record

Validated on 2026-10-30 using Python 3.14.2 and Node 25.2.1 on macOS.
Python 3.10+ is the intended baseline; other Python versions were not run here.
Node is only used for the development syntax check and is not needed to run the app.

## Automated checks

`python3 -m unittest discover -s tests -v`: **26 tests passed** in the final run.

- Retrieval ranking, source citations, unknown-query abstention, empty corpus,
  overlapping chunk boundaries, and four evaluation cases.
- All three bounded tasks, exact budget exhaustion, rejected task/budget values,
  and failed evidence review.
- SSE comments, multiline events, usage events, termination, truncated stream
  rejection, provider stream-error rejection, exact fixture timestamps, missing
  usage, empty output, and synthetic-mode labeling.
- Real HTTP adapter against a local mock SSE server, failure accounting without
  provider response leakage, and redirect rejection.
- Dashboard and status HTTP responses, RAG/agent routes, cross-origin rejection,
  malformed requests, and absence of a browser-accessible benchmark route.

The initial sandbox run passed 17 socket-free tests but could not bind local
test servers. A reviewed escalation enabled localhost sockets; the complete
suite then passed. No tests were skipped in the final run.

`node --check` of the dashboard's extracted JavaScript: **passed**.
CLI smoke checks for ask, completed safety task, budget exhaustion, and replay:
**passed**. `python3 -m lab evaluate`: **4/4 expected documents retrieved at k=3**.
These four fixtures are instructional, not held-out evaluation.

## Browser checks

Opened http://127.0.0.1:8080 in Chrome and verified:

- Retrieval submission displayed cited source passages with cosine scores.
- Evaluation control displayed the four fixture outcomes.
- Agent completion displayed a four-step plan/search/check/finish trace.
- Changing budget to three displayed budget exhaustion and no final answer.
- Synthetic replay displayed measured fixture TTFT, event spacing, event count,
  and unavailable token throughput, with the synthetic mode label.
- Screenshot inspection at a narrow browser viewport showed the responsive
  single-column layout and readable controls. Dedicated mobile-device and
  broad browser compatibility testing were not performed.

## Remaining limitations

No real LLM, neural embedding, vLLM server, or GPU benchmark was run. The adapter
was verified against a local mock only. No model weights were downloaded, no
cloud compute purchased, and no application deployed or externally pushed.

The three supplied Library screenshot references could not be downloaded.
Initial and one bounded retry both returned download failures. No readable
image bytes were obtained; no pixel inspection was claimed. The implemented
design follows the extracted agents/RAG/serving functional brief.

## GitHub preparation

Before the initial push, all 13 staged text files were inspected with focused
checks for provider tokens, private keys, credential-bearing URLs, secret
assignments, email addresses, and personal absolute paths. The only focused
matches were intentionally invalid URL fixtures in endpoint-rejection tests;
they contain dummy values, not credentials. No local outputs, environment
files, private keys, or downloaded artifacts were staged.

Gitleaks 8.30.1, downloaded from its official release with the published SHA256
checksum verified, found no leaks in the project directory. The final local
commit history is scanned before publication as well. These checks reduce
risk but cannot prove that every possible secret format is absent.

The full 26-test suite passed again after publication preparation. Runtime
authentication remains user-supplied through LAB_API_KEY in the environment.

## Frontend documentation update

Added an integrated Docs tab with seven sections: quickstart, architecture,
retrieval, agents, model setup, evaluation/metrics, and troubleshooting. Each
demo has contextual help and documentation links back to the demos. Hash routes
select sections without clearing demo results; the tabs support arrow keys and
Home/End.

The 26-test suite passed after this frontend change. The extracted JavaScript
passed `node --check`. Browser checks in Chrome verified Docs opening, repeated
tab and section clicks without duplicate content, direct section reload,
keyboard navigation, contextual help, and return navigation preserving retrieval
results. Retrieval evaluation, completed agents, budget exhaustion, and synthetic
serving replay continued to work.

Inspected the documentation at 1280, 390, and 320 pixel viewport widths. At both
narrow widths the page width matched the viewport width, with no horizontal page
overflow. Setup/model commands and troubleshooting text remained readable.
No new model integration, inference, dependency, or deployment was added.

## Scoped evaluation and abstention PR

The documentation update was published to main at
`adf7c4deb967845725d77e445936507f2a9e8ee6` before this branch was created.
The evaluation design was committed before implementation; 50 authored cases
and exact evidence spans were frozen before calibration. A 30-case development
split selected the lexical policy, committed before the first 20-case held-out
run. Both public splits are author-known; no independent human or model judge
was used. Cases and policy were not tuned after held-out scoring.

Final local checks: **48 tests passed** using Python 3.14.2, including all prior
agent, serving, HTTP and retrieval regressions. New tests cover span-union
arithmetic, multi-source evidence, fractional recall, exact provenance rather
than citation presence, modified output/unknown citation rejection, conservative
relevance precision, forbidden-span exposure, confusion-matrix denominators,
null denominators, stale annotations, corpus hashes, split validation, production
versus scored gate agreement, and held-out file-access rejection during calibration.

`python3 scripts/check_evaluation.py` passed: two byte-identical runs per split
match committed reports, and development-only calibration matches the frozen
policy. No performance threshold is asserted to make the suite appear successful.
`node --check` passed for the frontend JavaScript. Gitleaks directory scans found
no leaks; history and staged-content checks are repeated before branch publication.
Secret scanning is not a guarantee that every possible credential format is absent.

Browser checks verified supported extraction, unsupported refund-policy abstention
without answer passages, the explicitly labeled legacy smoke check, unchanged
agent completion and synthetic replay, and the revised Docs evaluation section.
At 390 pixels, documentation fit without horizontal page overflow. No real model,
GPU, private data, or networked inference was used.

The committed reports retain false abstentions, a conflicting-source failure,
and poisoned-instruction text exposure. Their limitations and denominators are
explained in `docs/evaluation-results.md`. CI is scoped to these deterministic
reports and stdlib tests on Python 3.10 and 3.14; it makes no model calls.

Independent-review follow-up: **56 local tests passed** after enforcing exact
fixture inventory and manifest hash coverage. Added negative tests for extra
corpus/profile/nested files, missing manifest entries, missing files, unused
profile references, and symlinks. A mutation test verifies the loader uses the
same document bytes it hashed. Development/held-out reports reproduce byte for
byte after refreshing evaluator-source hashes only; all scores, predictions,
dataset hashes, labels, split membership and policy values are unchanged.

## Optional cited-generation PR (#2)

PR #1 was merged at `6e8256ead29bd42bd4966a597741b48f4ad6bc1e`. Its push-triggered
post-merge CI run `41160635677` passed on Python 3.10 and 3.14 before this branch
was created. This branch uses a separate checkout; the user's main preview stays
on port 8080. The in-progress, explicitly offline shoe-policy preview uses 8091.

Local verification: **79 tests passed** on Python 3.14.2. New tests use local
deterministic HTTP fixtures and mocked TLS transport only; no live inference,
model weights, private documents or paid calls were used. Coverage includes
strict schema/citation validation, exact supplied-source provenance, no dispatch
on local insufficiency/disabled mode, model/provider abstention, refusal types,
truncation, redirects/no retry, errors without provider-body leakage, request and
response limits, deadline interruption, proxy isolation, TLS verification,
environment-only configuration, exact browser Origin/Host, forbidden browser
configuration, and concurrency bounds. Fixture success is not model quality.

The separately versioned 19-case contract suite passes, including an intentionally
citation-valid but false claim. `scripts/check_evaluation.py` reproduces frozen
v1 reports byte for byte; their corpus, labels, split, policy, core, and scorer
are unchanged. The fictional shop corpus is outside that manifest.

Frontend JavaScript syntax, IDs, labels, help links, default-disabled endpoint
selection and plain-text rendering paths passed static checks. Browser automation
became unavailable after the Mac disconnect, so the new PR #2 interface has NOT
received a rendered-browser or narrow-screen regression check. Do not interpret
static checks or HTTP 200 as visual verification. Both local previews respond
over HTTP; the earlier merged-main browser search had been verified before the
disconnect. Independent review should include the new interface when browser
automation is available again.

Generated semantic support is not assessed. A separate future review protocol is
in `docs/generated-support-review.md`; extractive v1 metrics are never applied to
generated paraphrases. No agent or benchmark improvements are included here.

Independent review of PR #2 reproduced valid JSON accepted after premature HTTP
EOF under an overdeclared Content-Length. The adapter now verifies declared byte
lengths before JSON parsing, rejects duplicate/ambiguous framing headers, and
requires complete chunk delimiters/terminal trailers. Decoder hooks are covered
by the supported Python CI matrix. Local framing regressions cover valid
length/close/chunked responses (including trailers), short bodies, missing zero
chunks, incomplete terminal trailers, malformed delimiters, and invalid headers.
The full **82-test** suite, frozen v1 report reproduction, 19 contract fixtures,
frontend static checks, and directory secret scan pass after these corrections.

Independent browser QA of the original PR #2 head verified shoe/receipt evidence,
helmet abstention, disabled endpoint messaging, Docs navigation/reload/repeated
clicks, existing demos, no console errors, and no page overflow at 320/390 pixels.
It identified clipped dropdown labels at 320 pixels and a policy-specific submit
label in the technical corpus. Visible options were shortened with full accessible
labels and contextual descriptions, and the button now says “Find matching text.”
The affected rendering needs a repeat check; static frontend checks alone do not
prove the clipping correction. The main 8080 preview is unaffected.

## Bounded model-agent PR (#3)

PR #2 merged at `27875cc733ce9f2a4cd48ac489ca5c7bdcf41642`; its post-merge CI
`41163223662` passed Python 3.10/3.14 before this isolated checkout was created.
The pre-code design is in `docs/bounded-agent-design.md`; the 23 authored agent
workflow fixtures were committed before runtime implementation. They are public
scripted contract regressions, not a live-agent quality study or blind split.

Local full suite: **99 tests passed** on Python 3.14.2. New checks cover runtime
allowlist enforcement independently of schema, discovered/read source provenance,
step/time/requested-output limits, malformed/forbidden choices, false-but-valid
negative control, missing/invalid reported usage, provider refusal/errors,
cancellation before requests/after responses/before tools, actual fake HTTP
search/read/finish round trips, in-flight server-side cancellation, active-job
capacity, retention eviction, endpoint opt-in/origin/body restrictions and the
preserved offline walkthrough. No live models or paid calls were used.

The per-case scripted report is `evals/agent-reports/v1-scripted.json`. Its fixture
inventory and hashes are validated, and the reported manifest identity comes from
the exact loaded snapshot. `scripts/check_agent_contract.py` reproduces it.
Frozen RAG-v1 reports and all generation contract fixtures remain unchanged and
pass their reproduction checks. They are not pooled with agent outcomes.

Frontend static checks pass. Polling/cancellation responses are keyed to their
job so stale responses cannot overwrite a later run, and Stop is disabled until
a job ID is known. Stop requests wait for terminal acknowledgment. A failed
start response is reported as an uncertain job outcome, not a confirmed stop.
Rendered-browser QA is still pending because the browser automation tool is not
available to this execution context after disconnection. Static/HTTP tests are
not visual verification; independent review should check the new agent controls,
trace, job cancellation, repeated starts, Docs and 320/390px layouts.

Existing preview ports 8080 and 8091 are preserved. The PR #3 preview is separately
served on 8092 with both endpoint features explicitly disabled. CritterDex port
4317 was not used or changed. No deployment, new credentials, shell/file-write
tools, live-agent quality claims, or serving-benchmark changes are included.

### PR #3 independent-review corrections

Both response-format modes now receive the full dynamic action contract in the
trusted system message, including schema version, exact fields, inactive-field
rules and discovered/read citation IDs. Payload assertions inspect all three
stages; negative mutations still fail local validation, and fake HTTP checks
verify JSON-object mode never silently switches formats. Offline accounting now
reports zero model requests and separate scripted decisions, with no model-request
trace events. Troubleshooting distinguishes the original four-step fixture from
the three-choice shoe walkthrough.

Independent browser QA of cd20f4a verified shoe/search/read/cite, two-choice
exhaustion, navigation/repeated fast runs, Docs/back/links, 320/390px layouts, no
console errors and existing RAG/replay. Those fast runs did not exercise Stop.
The new test-only Node harness executes the actual frontend submit, Stop, poll
and route functions using controlled pending responses and minimal DOM stubs. It
checks cancellation acknowledgment while navigating away/back, run-cancel-run,
late prior poll success/error, and late prior cancel responses. No stale response
replaces the next job or resurfaces a final answer after cancellation. Existing
Python fake-HTTP tests separately exercise a blocked in-flight provider request
and prove no tool executes after cancellation. These are handler/server checks,
not rendered-browser cancellation QA; actual delayed browser interaction remains
unverified. No production delays, live inference or dependencies were added.

After review corrections: **102 local tests passed** on Python 3.14.2. All frozen
RAG and generation suites reproduce; the 23 agent per-case outcomes and fixture
identity are byte-equivalent after excluding refreshed runtime source hashes.
The controlled-delay frontend harness and static integrity checks pass. Gitleaks
directory/history scans and focused staged-content checks are repeated before
publication; these cannot prove the absence of every possible secret format.
