# Reproducible serving suite v1 — design before implementation

Base: PR3 merge 6b953b1dfca41a91e9936ef9a9161fc76ac1569e. Preserve the legacy
benchmark/replay, frozen retrieval reports, generation and agent fixtures.

## Scope and workload

A finite client experiment, not a saturation study or hardware ranking. Three
public authored everyday prompts vary input length and requested output caps.
A seeded shuffle determines the repeated measured workload. Warmup uses the same
workload, runs before measurement, is recorded separately and excluded from all
measurement denominators/windows. Config: 1–30 measured requests, 0–3 warmups,
1–4 in flight, at most 10 dispatches/sec and at least 0.2/sec, 1–30sec/request.
Reject combinations whose conservative total run bound exceeds 180sec. No retries,
redirects, proxy inheritance, tokenizer estimates, or new credentials. Environment
only endpoint/model/key, HTTPS for non-loopback URLs, verified TLS. Keep browser
restricted to an offline virtual fixture; real traffic is CLI opt-in only.

## Measurement contract

Request start is the worker's monotonic timestamp immediately before connection,
not initial scheduler enqueue. First-content latency starts there and ends when
the first nonempty content delta is parsed; role/usage/heartbeat/header events
are not content. End is complete HTTP framing plus explicit SSE DONE and normal
finish. Gaps are between nonempty content events, not tokens. Reject malformed,
truncated, unfinished, error and refusal streams; discard partial timing/output
from success summaries. Retain bounded failure status/duration, never provider
bodies or output text. Errors/timeouts/refusals/incomplete streams are separate
counts and never successes. One choice only; normal finish is stop. Length-limit
and content-filter finishes are distinct non-success outcomes.

Latency p50/p90/p95 use nearest rank: sorted x[ceil(p*n)-1], null for n=0.
Publish n and estimator for every distribution, global and per prompt. These
small samples do not justify tail-latency generalization or confidence claims.
Per-request duration and first-content latencies summarize successes only; report
failure durations separately. Token counts are valid nonnegative integer provider
completion usage only. Missing counts remain unknown. Aggregate successful output
tokens/sec is sum of known successful completion counts / measurement elapsed
window (earliest measured worker start through latest measured completion,
including failures and rate pacing). Publish known-token coverage; do not label a
partial sum as full throughput. Full token throughput is null unless every success
has usage; no success gives null. Also report successful requests/sec using that
same window. This is client-observed mixed-workload throughput, not decode speed.

## Provenance and reproducibility

Report workload prompts/caps/IDs/hash, seed, config, run IDs, relative timestamps,
status counts, warmup outcomes and source version. Hash endpoint and model strings
for stable identifiers without serializing URLs/authentication. Optional human
model/hardware labels are operator supplied, restricted plain text; default not
supplied, never inferred. Record Python/OS family/architecture (no hostname, user,
absolute paths or env dump). Sampling temperature=0 and seed are sent explicitly;
provider may ignore/reject them; no guarantee of deterministic model responses.

Offline UI/CLI fixture uses deterministic virtual timestamps and explicitly
synthetic fixture token counts, never a real model performance claim. Keep fixture
artifacts separate from real reports and other evaluation suites.

## Tests planned before code

Known timestamp arithmetic and nearest-rank edge cases; usage absent/invalid;
role/heartbeat ignored; interleaved streams isolate each request; real localhost
fake streaming server with warmup exclusion, caps and concurrency/rate bounds;
refusal/provider error/truncation/disconnect/timeout/length finish; framing and
response/line limits; no redirect/proxy/auth on insecure remote; endpoint/model
not leaked. Scheduler finite requests and bounded inflight, no retries. Versioned
synthetic report reproduces; CLI, API-only-offline and frontend static checks.
Browser QA should check readable report/slices/caveats and existing workflows at
320/390px. No paid/live model, GPU, secrets or deployment in implementation/testing.
