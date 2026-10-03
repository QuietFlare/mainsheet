# Practices

Each entry names a rule this repository follows, why, and where it is applied.
An entry is added in the same commit as the code that applies it. Observations
go in the README; this file holds rules only.

## Validate inputs before the first model call

The model is the most expensive and least predictable component. Anything a
program can decide, it decides first, and refuses early with a clear message.
Applied in `mainsheet/agent/config.py`, `preflight()`, and each tool module's `preflight`.

## One emit point, several sinks

Every step is recorded through one call. Where it goes, a JSON line on disk and
an event on the current span, is decided in one file.
Applied in `mainsheet/agent/events.py`.

## Tokens are facts, cost is a rate applied later

Token counts come from the API and never change. Price is a dated rate. Both are
stored, with the estimate labelled by its source, so any run's cost can be
recomputed. Applied in `mainsheet/agent/runtime.py`, the `run.ended` event.

## The tool function is the security boundary

The model sees a name, a description and a schema. Only the function runs.
Every limit that matters is enforced inside the function, never in the prompt.
Applied in `mainsheet/agent/tools/notes.py`.

## Tools are bound to one agent when built

A tool module exposes `make_server(agent)`. The server it returns can act only
within that agent's scope. Two agents get two servers.
Applied in `mainsheet/agent/config.py`, `build_options()`.

## Remove every tool the task does not need

`tools: []` strips the built-ins, so the agent has exactly the capabilities in
`allowed_tools`. Applied in `mainsheet/agent/config.py`.

## Compose tool errors for the model

A raw exception tells the model nothing it can act on. Handlers catch failures
and return `is_error` with a message that says what was wrong.
Applied in `mainsheet/agent/tools/notes.py`.

## Tool handlers never block the event loop

Subprocess and network calls run through `asyncio.to_thread` or an async client,
so one slow tool cannot stall other instances. Applied in `mainsheet/agent/tools/notes.py`.

## One schema, three enforcement points

The definition's pydantic model validates the file, the panel's API and the
panel's form, which reads the schema for its limits and lists.
Applied in `mainsheet/agent/config.py`, `mainsheet/panel/app.py`, `mainsheet/panel/canvas.html`.

## The gate decides before every call, in code

The policy table is enforced by a PreToolUse hook. The model is asked what it
wants, never whether it may. A denial stays in force for the run.
Applied in `mainsheet/agent/policy.py`.

## Every refusal is an incident

Denials carry severity, rule, tool, argument digest and policy version, and are
counted on the instance. Applied in `mainsheet/agent/runtime.py`, `record_decision()`.

## Task-creating endpoints run on the event loop

Anything that creates or cancels an asyncio task is an `async def` endpoint.
File-only endpoints stay plain `def` so FastAPI keeps them off the loop.
Applied in `mainsheet/panel/app.py`.

## The panel holds no state of its own

It reads and writes files and calls the registry. A reload, a second browser,
the CLI and CI see the same system. Applied in `mainsheet/panel/app.py`, `mainsheet/agent/system.py`.

## Share the specification, withhold the cases

The agent is told the format and meaning of its output. It is never shown the
eval fixtures. Applied in `mainsheet/evals/generate.py`.

## Generated tests are proposals

A test nobody has read is not a test. The generator writes to `*.proposed.yaml`;
a person renames it after review. Coverage of the taxonomy is checked by code.
Applied in `mainsheet/evals/generate.py`.

## The runtime contract is enforced on generated tests

What the runtime makes definite, the lint rewrites. What needs judgement, it
flags. Applied in `mainsheet/evals/generate.py`, `lint()`.

## A judge sees only the output

Quality checks go to a separate model in a fresh context, never the agent that
did the work, and never with the tool calls. Assertions about tools belong in
behaviour. Applied in `mainsheet/evals/run.py`.

## Follow-ups

- The agent name rule is defined in three places. Move it to one constant.
- The model list is a constant. Fetch it at startup once an API key is used.

## Egress is a process boundary, not a rule

A rule the gate applies can be argued with or retried; a closed socket cannot.
The policy's `network.allow` list is handed to the harness sandbox, which
denies every other host to every command the agent runs. Empty means none.
The gate never sees a socket; it sees the sandbox's violation report in the
tool result and records it as a critical incident. Applied in
`mainsheet/agent/config.py`, `sandbox_settings()`, and `mainsheet/agent/policy.py`, `Gate.post()`.
