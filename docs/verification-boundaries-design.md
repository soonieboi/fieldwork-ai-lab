# Final verification/boundary scope — PR5

Base PR4 merge d795723ec98b2b5948678cb92f4bea340aee5837. Existing reviewed
transport already enforces HTTPS outside loopback, TLS verification, no proxy/
redirect/retry, bounded framing/body/deadline checks. Existing model adapters have
separate opt-ins/credentials and no browser-selected endpoints. Agent tools,
budgets/cancellation and all RAG/generation/agent/serving fixtures stay unchanged.
Do not duplicate them or imply fixture success establishes live model quality.

Concrete gaps to fix: local HTTP tests use urllib's cached global proxy opener;
Host validation currently protects only generation/jobs; incoming Content-Length
is parsed permissively without duplicate/Transfer-Encoding checks; short/slow
bodies and duplicate/nonfinite JSON need consistent rejection. Add fixed response
headers and CSP for the single trusted script, preserving current inline styles.
Keep loopback binding, reject foreign/duplicate Host, finite body read, close
connections after each response and fixed sanitized malformed-body errors.
This is not authentication, full DoS protection or production HTTP parsing.

CI: checksum-pinned official Gitleaks 8.30.1, full fetched history plus tracked
working-tree snapshot, redacted output, generated dummy negative control proves
the scanner actually detects a leak. No real secrets, scan bypass/allowlist or
untrusted PR write permissions. Locked test-only Playwright package and pinned
GitHub actions; Chromium runs only in the disposable CI runner with endpoint
features disabled and network blocked except the isolated local app. Browser
smokes cover everyday retrieval, abstention, agent run, replay, synthetic batch,
Docs navigation/reload, security-header compatibility, console errors and
320/390px overflow. Existing controlled-delay agent harness remains separate.

Tests should prove bad Host/framing/JSON rejected before work, finite short/slow
body behavior, response headers and CSP compatibility, no arbitrary file serving,
loopback bind, and proxy independence despite empty NO_PROXY/cached bad opener.
Don't globally change the user's proxy/browser settings. No models, private data,
paid calls, deployments, auth infrastructure or persistent permission changes.
Record threat model, residual local-process/DoS/provider/prompt risks, and a
nonproduction checklist. Stop at draft PR for independent review.
