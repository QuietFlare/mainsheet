# ADR 0004: Shared memory and a gated channel come before any swarm support

Status: proposed

## Context

Mainsheet runs one agent per instance. The registry can hold several instances, but they do not know each other and nothing passes between them.

A measured research run of sixteen questions took about a hundred tool calls, most of them web search and fetch, with every fetched page entering the context in full. Splitting the same questions across three agents would cut the wall time to a third and raise the cost: each agent would fetch the same source pages, carry its own copy of the instructions, and reason over the same material independently. Parallel agents reduce time, not tokens.

A swarm's cost has three parts that can be paid once and three that cannot. Shared: the request prefix (tools, system prompt, common documents), which the API serves from cache at about a tenth of the input price for every agent after the first; the pages and documents the agents read; the model tier of agents that only read and extract. Not shared: each agent's reasoning, each agent's output, and the messages agents exchange, which every recipient reads in full.

Agents that share any channel coordinate through it. METR's multi-agent evaluation observed roles and coordination emerging among roughly 1,200 agents through a shared cache path that no prompt mentioned. A runtime whose purpose is a record of what the agent did cannot leave such a channel unrecorded.

## Decision

Mainsheet gets no orchestrator and no swarm runtime. Two tool servers come first, and only after someone outside this project says they want them.

A memory server. One MCP server with three tools: remember, recall, list. An entry holds a digest, the source URL, a hash of the source content, the agent that wrote it, and the time. The first agent that reads a page stores a digest; every other agent asks the memory before the web. Because it is an MCP server it runs under any runtime that speaks MCP. Under Mainsheet the policy gates remember and recall like any other tool, and the trail records every write, so every fact an agent remembers was written through a rule.

A channel server, later. The only way two instances talk. Every message is a gated tool call and a trail record.

The budget for a swarm sits above the agents, one cap drawn down by every call from every instance, once more than one instance can run on purpose. Until then the per-run cap stands.

Agent-specific prompt text goes after the shared text in every definition, so the cached prefix survives across agents. This is a rule for agent authors, written into the definition docs, not enforced by the runtime.

## Consequences

Mainsheet stays a gate and a record. Working memory across runs and across agents lives in a tool server the policy sees, not in the runtime.

The memory server is the first independent module: its own repository, its own licence, usable without Mainsheet. The channel server is built only when a user outside this project asks for it.

What this does not give: shared reasoning. A swarm with shared prefix, shared memory and cheap readers costs less than a naive swarm and more than one agent in sequence. Mainsheet's default stays one agent, resumed when it stops.
