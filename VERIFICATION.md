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
