# Documentation-assistant evaluation contract — v1

Status: pre-implementation design for the first improvement PR. This contract
covers deterministic retrieval and extractive responses only. It does not assess
LLM generation, model reasoning, agents, tools, or serving performance.

## Task and corpus boundary

Given one English question about the local Fieldwork lab, return source excerpts
only when there is adequate evidence for the requested information; otherwise
abstain. Questions that require choosing between unspecified metrics, resolving
conflicting sources without a precedence rule, revealing credentials, or obeying
instructions embedded in source text are outside the answer contract.

The evaluation uses a versioned, byte-frozen snapshot of the four authored sample
Markdown documents from the app at commit adf7c4deb967845725d77e445936507f2a9e8ee6.
They describe this starter, not general vLLM product support or service policies.
Per-case profiles may add explicitly synthetic conflicting statements or an
instruction-bearing document. Profiles do not alter the app's default corpus.
A manifest records every corpus file hash. No private documents, user queries,
production traffic, fetched content, credentials, or paid model calls are used.

All questions and gold evidence annotations are authored for this task. No
independent human or model judge is involved. Gold labels are author assertions,
validated structurally against exact source spans; they are open to review.

## Dataset and split discipline

Version v1 contains 50 cases: development 30 and held-out 20. Proposed category
counts are 16/10 answerable, 8/4 unanswerable, 2/2 ambiguous, 2/2 conflicting,
and 2/2 adversarial (development/held-out). A category is a slice, not necessarily
a disposition: an adversarial case may still have an answerable factual question
if the source injection is to be ignored. Every case records its expected
`answer` or `abstain` disposition and a rationale.

Case IDs, split membership, profiles, questions, and gold annotations are frozen
before calibration. Both splits are public and authored by the same agent, so
"held-out" means excluded from tuning, not independently blind or an estimate
of out-of-distribution generalization. Related paraphrases of the same facts
may occur across splits; this limits independence and must be disclosed.

Calibration reads development cases only. Freeze and commit the chosen lexical
gate configuration before the first held-out run. Do not change thresholds,
question wording, or labels in response to held-out results. Fixing a held-out
label or behavior later requires a new dataset/policy version and explicit
contamination note; keep the original report. Report development and held-out
separately and never pool them into a flattering headline score.

## Unit and gold labels

The evaluation unit is `(question, corpus profile)` with a fixed chunker (85 words,
15-word overlap), tokenizer, search k=3, and deterministic tie-break order.

For each case record: ID, category, disposition, profile, rationale, and zero or
more required evidence spans. A span has a source filename and exact quoted
text that must occur exactly once in that document. Resolve it to half-open word
offsets with the same whitespace tokenization as the chunker. Some cases need
multiple spans or multiple sources. An unanswerable case may have no relevant
span; ambiguous/conflicting cases can label diagnostic evidence without being
answerable. Adversarial cases additionally label forbidden instruction spans.

Use offsets and source identity to score evidence. Matching an arbitrary keyword,
merely emitting a citation, or retrieving a whole expected filename is not an
answer-success rule. Gold span validation must reject missing, duplicate, empty,
or stale annotations before scoring.

## Separate measurements, with denominators

Do not collapse these into one quality score.

1. Retrieval: required-evidence token recall@3 (union of retrieved chunk spans
   intersecting each required span), complete evidence-set coverage@3, and MRR
   of the first chunk overlapping required evidence. Score only cases with gold
   evidence; report the eligible count. MRR is a coarse relevance signal, while
   full coverage prevents a tiny overlap from counting as sufficient evidence.
2. Evidence sufficiency: compare the system's answer/abstain decision with the
   authored disposition. Report a confusion matrix, false answers, unnecessary
   abstentions, and slice denominators. Diagnostic evidence does not make an
   ambiguous/conflicting question answerable.
3. Extractive answer support: for answered cases, verify exact provenance of
   returned text and citation IDs against actual source chunks, not citation
   presence. On answered answerable cases, separately report required-evidence
   recall and complete coverage. Report gold-evidence token precision as a
   conservative relevance proxy: background text outside labeled spans counts
   against it even if factually true. Report forbidden-span exposure when labeled.
   Semantic factuality and claim entailment are NOT ASSESSED. Exact extraction
   proves provenance, not that the passages answer the question.
4. Abstention: report correct abstentions / gold-abstain cases, unnecessary
   abstentions / gold-answerable cases, and answer coverage / all cases, separately
   for every split, profile, and category. Undefined denominators yield null,
   never an invented zero or perfect score.

Include per-case predictions, source IDs, raw gate features, label rationales,
failure reasons, and a bounded set of concrete failures. Record dataset/corpus,
policy, and source-code hashes. Reports have stable ordering and no timestamps,
randomness, or network calls, so identical inputs produce byte-identical JSON.

## Baselines and calibration

Compare the existing positive-score TF-IDF extractive baseline (always return
retrieved passages when any positive similarity exists) against a conservative
lexical gate. Keep retrieval/chunking unchanged between the two systems, so
retrieval scores should be identical. A gate improvement is a decision tradeoff,
not a retrieval improvement.

The gate may use only top cosine similarity and query content-term coverage in
the retrieved excerpts. Its fixed question-word stoplist must be documented.
No regex matching individual evaluation questions, case IDs, category labels,
gold dispositions, special conflict profiles, or test-specific vocabulary is
allowed in production decision logic. There is no claim of semantic sufficiency,
conflict detection, prompt-injection defense, or confidence calibration.

Predeclared grid: minimum top score in {0.0, 0.10, 0.15, 0.20}; minimum content-term
coverage in {0.0, 0.50, 0.75, 1.0}. Minimize `2 * false_answers + unnecessary_abstentions`
on development only; ties prefer higher content coverage, then higher similarity.
The 2:1 penalty is an authored conservative tradeoff, not empirical user utility.
Always abstain on no evidence or no content terms. Commit the full calibration
trace and selected configuration before scoring held-out cases.

Apply the selected gate to the default app's `Index.answer` and preserve the raw
`search` interface and explicitly labeled legacy smoke evaluation. Add decision,
reason, and gate-feature fields without inventing generated answers. Abstention
must not display retrieved passages as though they were an answer; diagnostic
retrieval evidence may be retained in a separate field.

## Expected weaknesses and acceptance criteria

Lexical gating will reject some supported paraphrases and accept some unsupported
questions sharing known vocabulary. It cannot resolve conflicting facts or
understand malicious instructions. Small, correlated synthetic slices cannot
support production, security, fairness, or model-performance claims.

Acceptance is reproducibility and honest scope, not an arbitrary accuracy target:
validate all labels/splits/hashes, show baseline comparisons with denominators,
exercise scorer arithmetic and negative mutations, preserve existing agent and
serving regressions, and keep credentials out of code/artifacts. CI should run
stdlib tests and verify deterministic committed reports. It must not call a model
or upload private input. Agent task success/tool safety and serving latency/load
need separate future designs and suites.
