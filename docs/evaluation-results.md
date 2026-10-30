# v1 documentation-assistant baseline results

This is an authored synthetic evaluation of exact source extraction and an
answer/abstain decision. It is not an LLM evaluation, a human judgment study,
a prompt-injection defense test, or a production quality claim. See
[evaluation-design.md](evaluation-design.md) for the pre-implementation contract.

## Freeze and execution order

1. Design committed at `5c9d0e3` before implementation.
2. Corpus, exact evidence spans, 30 development cases, and 20 held-out cases
   frozen at `bed7ced`; `evals/v1/manifest.json` records file hashes.
3. Development-only grid search selected top cosine >= 0.20 and query content-term
   coverage >= 0.50. Policy and all 16 candidates committed at `6bb9b06`, before
   the first held-out evaluation. Objective: 2 * false answers + unnecessary
   abstentions. This authored preference is not measured user utility.
4. Development and first held-out reports committed at `559c58b`. No question,
   gold label, source, threshold, or scorer was changed in response to held-out
   results. Later CI reruns check reproducibility, not model selection.

The public held-out split is author-known, not independently blind. Related facts
and paraphrases occur in both splits. The base corpus has only four instructional
documents, with explicit synthetic conflict/poison overlays. Slice sizes of one
to sixteen cases are too small for robust generalization or security claims.

## Decisions — development only (30 cases)

There are 17 gold-answerable cases and 13 gold-abstain cases. Category counts
are 16 answerable, 8 unanswerable, 2 ambiguous, 2 conflicting, and 2 adversarial.
One adversarial case is factually answerable, so category and disposition differ.

| Decision measurement | Original positive-score extraction | Lexical gate |
| --- | ---: | ---: |
| Gold-abstain cases answered (false answers) | 11/13 | 3/13 |
| Gold-abstain cases correctly abstained | 2/13 | 10/13 |
| Gold-answerable cases unnecessarily abstained | 0/17 | 3/17 |
| Cases answered, regardless of correctness | 28/30 | 17/30 |

The gate's remaining false answers are one ambiguous latency question and both
conflicting-budget questions. It unnecessarily refuses supported questions about
the RAG pipeline, retrieval metric, and agent tools.

## Decisions — held-out only (20 cases)

There are 11 gold-answerable cases and 9 gold-abstain cases. Category counts are
10 answerable, 4 unanswerable, 2 ambiguous, 2 conflicting, and 2 adversarial;
one adversarial case has an answerable factual request.

| Decision measurement | Original positive-score extraction | Lexical gate |
| --- | ---: | ---: |
| Gold-abstain cases answered (false answers) | 7/9 | 1/9 |
| Gold-abstain cases correctly abstained | 2/9 | 8/9 |
| Gold-answerable cases unnecessarily abstained | 0/11 | 2/11 |
| Cases answered, regardless of correctness | 18/20 | 10/20 |

These are decisions versus authored answerability labels, not counts of verified
correct natural-language answers. The gate changes coverage as well as error
rates; presenting only the lower false-answer count would hide the tradeoff.

## Retrieval and output evidence are separate

Retrieval is identical in both baselines: the gate does not change chunking,
ranking, or k. Development complete evidence-set coverage is 22/22 eligible
cases; held-out coverage is 14/15. Held-out MRR is 0.866667 over 15 evidence-labeled
cases. Diagnostic evidence for an ambiguous/conflicting request counts toward
retrieval but does not turn that request into an answerable one. Cases with no
gold evidence are excluded from retrieval denominators.

Exact extractive provenance passes for every returned answer in both baselines.
That only means the excerpts and chunk IDs match source bytes. It is not semantic
correctness, entailment, or prompt-injection resistance. All nine answered,
gold-answerable held-out cases from the gate cover their complete gold evidence.
But their average gold-evidence token precision is only 0.060125: most returned
chunk text lies outside the narrow annotated answer spans. Unlabeled background
can be true; this is a conservative relevance proxy, not a hallucination rate.

The poisoned-source instruction is exposed as quoted text in 1/1 eligible
poisoned cases in each split, for both baselines. No instruction is executed and
no tool privilege exists here. We measure source-text exposure, not model
obedience or agent tool safety. Those need separate future evaluation designs.

## Concrete held-out failures (unchanged after scoring)

- `held-02`: “Is the lab planner a real LLM?” has explicit evidence, but the gate
  abstains because lexical support does not clear the frozen threshold.
- `held-08`: “How are API credentials stored according to the lab?” is supported,
  but the lexical gate unnecessarily abstains.
- `held-18`: “Which document is authoritative about the agent budget?” is not
  answerable from the conflicting profile, yet the gate returns excerpts.
- `held-20`: “Does the local lab server bind to 127.0.0.1?” is answerable, but the
  returned excerpts also expose the synthetic poisoned instruction.

All cases, raw features, evidence IDs, source/policy hashes, per-category and
per-profile denominators are in `evals/reports/v1-development.json` and
`evals/reports/v1-heldout.json`. No scores are pooled across splits. No semantic
judge, LLM, real agent evaluation, or serving benchmark is represented.

## Reproduce

From the project root, with Python 3.10 or newer and no added dependencies:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_evaluation.py
python3 -m lab eval-suite --split development --output results/development.json
python3 -m lab eval-suite --split heldout --output results/heldout.json
```

`check_evaluation.py` recalculates calibration on development only, checks it
matches the frozen policy, then runs each split twice and compares canonical
JSON bytes with committed reports. It does not optimize against held-out output.
`python3 -m lab evaluate` remains a separately labeled four-question legacy smoke
check; its 100% result must not be substituted for this evaluation.

Future iterations should version the policy/dataset and treat v1 held-out cases
as exposed regression data. A stronger generalization claim needs new independent
questions, broader documents, reviewed labels, and uncertainty reporting.
