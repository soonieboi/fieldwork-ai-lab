# Serving and measurement

vLLM can expose an OpenAI-compatible chat completions endpoint. Configure the endpoint and model explicitly. A GPU and separately provisioned model are required for typical vLLM deployments; this lab does not install vLLM or download weights.

Time to first token (TTFT) measures from request start to the first nonempty content delta observed by the client. Inter-token latency (ITL) needs token-level timestamps. A streaming API may deliver multiple tokens in one event, so this lab reports inter-content-event latency instead of claiming true token latency.

Output throughput uses completion token counts reported by the server divided by total request duration. If token usage is missing, token throughput is unavailable. A sequential benchmark of one client is not aggregate server throughput or a saturation test. Record failures and warmup policy alongside latency percentiles.
