# Lab operations

The lab server binds only to 127.0.0.1. Browser requests can search the bundled corpus, run bounded tasks, and replay synthetic streams. Real serving requests are available only from the CLI and require an explicit endpoint. This keeps the browser from choosing arbitrary network targets.

The server accepts small JSON requests and rejects unknown tasks and out-of-range step limits. There is no shell tool. Agent runs have a fixed budget of at most six steps. Sample documents are instructional fixtures and contain no private data.

Use synthetic stream replay to test the metric parser offline. Replay timings reflect local fixture delays, not model performance. The real adapter sends only a fixed public benchmark prompt, never retrieved documents. Keep API credentials in environment variables and never commit them.
