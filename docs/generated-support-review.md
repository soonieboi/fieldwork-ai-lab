# Generated-output support review — separate from v1 extraction eval

Status: review rubric only. No live samples, independent human judgments, model
judge, or semantic quality scores have been collected for this PR.

## Three different questions

1. **Contract validity:** did JSON, types, bounds, finish status, and exact citation
   IDs pass local validation? The 19 authored contract fixtures test this.
2. **Source provenance:** does each cited ID point to a chunk actually supplied
   to that request, with the original source bytes/offsets/hash? The adapter
   checks supplied chunk provenance. This does not assess the claim's meaning.
3. **Factual support:** does the cited text justify each generated claim, including
   all conditions and uncertainty? This needs a separately scoped review, not
   citation presence, word overlap, or extractive token precision.

A deliberately contradicted claim in the contract fixtures has valid JSON and a
valid citation. It is accepted by the contract validator. This is intentional:
acceptance is not a fabricated semantic judgment or a claim of safe generation.

## Example, not a model result

The invented Maple Street Shoes policy says shoes bought here can be returned
within 30 days if unworn and accompanied by a receipt. The everyday prompt says
10 days and unworn, but does not establish that the shopper has a receipt.

An authored, condition-preserving example is: “The time and condition requirements
fit; you still need a receipt.” An unconditional “Yes, you can return them” would
need scrutiny for the missing receipt condition. “Can I return a bicycle helmet?”
cannot be resolved from the sample policy. No real shop or real purchase is involved.

These explanations are author reasoning about a fictional policy, not human/model
judgments of any live completion. The lexical pre-gate remains fallible; the
adapter's prompt cannot guarantee that a provider handles uncertainty correctly.

## Future authorized review protocol

Before collecting real samples, fix task/corpus boundaries, sampling strata,
model/configuration, inclusion/exclusion rules, and the development versus
held-out plan. Get authorization for the endpoint and data being sent. Do not
reuse exposed v1 questions to tune generation and call the result held-out.

For every sampled request, retain appropriate non-private evidence for review:

- Question/corpus snapshot and document hashes; retrieved IDs/excerpts and the
  gate decision, including refusals that caused no request.
- Endpoint/model version, chosen response format/token parameter, prompt version,
  and bounded configuration. Never credentials or private endpoint identifiers.
- Raw completion retained only with appropriate permission; validated claims,
  their cited IDs, contract failures, provider refusals, and truncations.
- Reviewer identity/provenance, date, and one verdict per claim: **supported**,
  **contradicted**, **insufficient evidence**, or **not assessable**. Require an
  evidence location and rationale; assess each condition, quantity and negation.
- Separate question-coverage and abstention judgments. A perfectly supported
  partial claim can still fail to answer the question. Track malicious-source
  instruction exposure/obedience separately; a schema test cannot establish safety.

Report every slice and denominator: attempted requests, pre-gate abstentions,
provider failures/refusals, valid/invalid contracts, generated claims reviewed,
coverage judgments and missing/not-assessable reviews. Do not drop failed requests
or pool contract pass rates with support rates. Define treatment of correlated
claims and repeated questions, uncertainty intervals, independent second review,
and disagreement adjudication before reporting a generalization claim.

## Preservation boundary

`evals/v1`, `evals/reports/v1-*`, the lexical policy and scorer are frozen. They
remain extraction/decision regressions only. The new shop example is separate.
Generated paraphrases are not assigned extractive word-offset precision scores.
`evals/generation-contract-v1` contains synthetic protocol inputs, not generated
model output or semantic gold labels. No answer-quality benchmark is claimed.
