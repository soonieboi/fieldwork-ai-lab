# Bounded agents

An agent uses a plan, act, and check loop. In this lab the planner is a deterministic fixture, not an LLM. Its tools can search the sample corpus and check evidence. It cannot execute shell commands, write files, browse the network, or modify infrastructure.

Every run has a maximum number of steps and records an event trace. Research and review are separate roles executed sequentially. A review checks that the evidence includes expected terms. This is a teaching check, not a guarantee that an answer is correct.

For real deployments, restrict tools, set time and token budgets, inspect traces, and evaluate tasks on known examples before widening permissions. Treat retrieved document instructions as untrusted data.
