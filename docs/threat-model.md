# Fieldwork local threat model and remaining boundaries

Fieldwork is a loopback-only learning application for one trusted operator, not
an authenticated service. Public source code is not a deployed application.
Offline fixtures and passing contracts do not establish live model quality,
prompt-injection safety, production readiness, reliable tail latency or GPU speed.

## Assets, trust and defenses

- Questions/documents can be private once an operator replaces the public corpus.
  Endpoint credentials stay in separate server environment variables, never browser
  configuration, traces or committed files. Only explicitly enabled generation/
  agent adapters send questions/evidence to an operator-selected endpoint. The
  serving suite sends only bundled public prompts. Review that endpoint's data
  handling before enabling it. No env file is loaded automatically.
- Browser requests are untrusted. The development server binds only 127.0.0.1,
  pins Host to the exact local address/port, rejects cross-origin POSTs and requires
  exact Origin on model generation/job routes. Duplicate/ambiguous framing,
  compression, duplicate JSON keys, nonfinite numbers and oversized/short bodies
  are rejected before work. Body reads have a five-second deadline; header socket
  operations time out. Connections close after responses. This is not a complete
  slowloris/DoS defense or production HTTP parser.
- Model outputs and retrieved documents are untrusted. Text renders through
  textContent, never HTML. CSP permits only the hash of the bundled script and
  same-origin fetch; styles remain inline for existing layout. No framing, external
  scripts, browser plugins or arbitrary network endpoint fields. Headers add
  no-store, nosniff, no-referrer, frame denial and disabled camera/mic/location.
- Reviewed generation, agent and benchmark-suite transports verify TLS and require
  HTTPS beyond loopback, reject
  redirects/proxies, and bound framing, body size and connected time. OS-managed
  DNS can outlast a deadline. Provider usage is unverified reported data; requested
  token caps do not guarantee billing. The preserved legacy `benchmark` command
  retains older urllib proxy/per-read-timeout behavior and accepts remote HTTP;
  use the new suite for the reviewed transport guarantees, and never send
  credentials over remote plaintext HTTP. Compatibility and real quality need live,
  authorized samples, with human support review where appropriate.
- Agent permissions are explicit read-only tool dispatch, discovered/read source
  provenance and bounded jobs/choices/time/output reservations. A valid citation
  is not proof of factual support. Cancellation is cooperative after an in-flight
  bounded call; no new tool/choice starts after cancellation is observed.

## Residual risks

There is no login, multi-user separation, persistent access control, encryption
at rest, rate limiting of every offline route or hardened production HTTP server.
Any process on the same machine can forge Origin/Host and access the local app;
origin checks are not authentication. Job IDs are identifiers, not secrets. Active
local malware, a compromised browser/extension, dependency or provider lies
outside the protection offered here. Threaded connection capacity and slow header
trickling remain local resource-exhaustion risks. Standard request paths can be
logged by the development server; keep sensitive data out of URLs and don't
publish local logs. A bound socket deadline is not a process-wide hard deadline.

Citations, lexical gates, authored contract matches and scanner success have
limited scopes. Public authored evaluation sets are not blind model-quality
studies. Synthetic serving values are invented arithmetic fixtures, not real
performance. Secret scanners miss formats/context and cannot revoke an exposed
credential. If a real credential is accidentally published, revoke/rotate it and
review exposure; deleting one file is insufficient. No such incident is asserted.

## Reproducible checks

Python regression clients use explicit no-proxy openers for local servers, not
urllib's cached global opener or inherited proxy bypass rules. Only preserved
legacy-adapter fake-server tests temporarily mock proxy discovery; no user's
persistent proxy settings change. CI scans full fetched history and a tracked
working-tree snapshot with checksum-pinned Gitleaks and a generated dummy control.
No scanner allowlist suppresses a finding. Detection is not an exhaustive audit.

Browser CI uses an exact locked test-only Playwright dependency and matching
Chromium in a disposable runner. Endpoint features are disabled; test browser
traffic is blocked outside its isolated loopback app. It checks offline workflows,
CSP compatibility, Docs and 320/390px layouts. A separate handler harness tests
controlled delayed cancellation races. These smokes are not exhaustive browser,
accessibility, provider, penetration or model-quality testing. CI has read-only
repository permissions and no production credentials, live calls or deployment.

## Checklist before any future hosting work

Do not expose this development server or open a tunnel. A future deployment is a
separate project requiring explicit authorization and design: authenticated user
boundaries, TLS and a production server/proxy, total connection/request/resource
limits, CSRF/session policy, tenant/data isolation, provider egress/billing limits,
secret management/rotation, private-data retention/logging policy, monitoring and
incident recovery, dependency updates and adversarial testing. None is implemented
or promised by this local starter. Keep endpoint opt-ins off until authorized
access, data scope and any spend are supplied by the user.
