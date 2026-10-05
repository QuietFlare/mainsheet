# Mainsheet

An agents runtime: define an agent in one file, run it governed, prove what it did.

Mainsheet executes agent definitions with the guarantees agents need. A policy
gate decides before every tool call, in code the model never sees. Budgets cap
turns, calls, time and cost. Every step is an event on disk and a span in your
tracing backend. Every refusal is a violation. A generated, reviewed eval suite
says how the agent behaves under injection, contradiction, missing input,
sensitive data, scope creep and forbidden tools.

The mainsheet is the line a sailor holds to keep the sail under control.

## Install

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
```

Python 3.11 or later. The model is reached through the Claude Agent SDK. Set
`ANTHROPIC_API_KEY` to bill a run to the API. With no key set, the SDK uses a
stored Claude login, which is for your own local runs. Each run prints the
credential it found before the first model call.

## Run

```bash
mainsheet                 # run agent.yaml once, print each step, write trail/events.jsonl
mainsheet-verify <id>     # check the signed record of every gate decision in the run instances/<id>
mainsheet-panel           # canvas at http://127.0.0.1:8765: create, configure, connect, run, watch
mainsheet-evals-propose   # propose an eval suite for agent.yaml, one case per misalignment category
mainsheet-evals evals/suites/mainsheet.yaml
pytest                    # unit tests for the gate and the eval tooling
```

Mainsheet writes `instances/`, `trail/`, `agents/` and `system.yaml` in the
folder you run it from. Set `MAINSHEET_HOME` to use another folder. With no
`agent.yaml` there, `mainsheet` runs the example that ships with the package.

Optional viewer for traces: `docker run -d -p 6006:6006 arizephoenix/phoenix`
and open http://localhost:6006.

## An agent

```yaml
name: standup
model: claude-sonnet-5
max_turns: 6
timeout_s: 300
system_prompt: Use tools only for the task given.
task: Read the note titled 'Standup'. Write 'Standup summary' with three lines. Then stop.
tools:
  builtin: []
  servers:
    notes:
      module: mainsheet.agent.tools.notes
      allow: [notes_read, notes_write]
policy:
  version: 1
  tools:
    notes_read: {}
    notes_write:
      irreversible: true
      args: {title: {pattern: "^Standup"}}
  deny_patterns:
    - {pattern: "curl .*\\| *(ba)?sh", reason: remote content piped into a shell, severity: critical}
  budgets: {max_tool_calls: 10, max_cost_usd: 0.50}
```

One schema validates this file, the panel's API and the panel's form.

A server may also be a program Mainsheet starts and speaks MCP to, in
place of a module: `command: ${MAINSHEET_PYTHON}` with `args:` and
`env:`. `${NAME}` expands from the environment, `${NAME:-}` may be unset,
and `MAINSHEET_PYTHON` is the interpreter running Mainsheet.

## What the runtime guarantees

- **Tools are bound to one agent when built.** A tool module exposes
  `make_server(agent)`. The Notes tools write only into that agent's folder.
- **The gate runs before every call.** Unknown tool, disallowed tool, argument
  outside its pattern, deny pattern match, budget reached, human approval
  required, or an irreversible tool after untrusted output: each is refused
  with a reason the model reads. A refused call stays refused; a retry does not
  get a fresh decision.
- **Commands cannot reach the network unless the policy says so.** Every
  command the agent runs is sandboxed by the harness (Seatbelt on macOS,
  bubblewrap on Linux) with egress limited to `policy.network.allow`, empty
  by default. A blocked connection is a `sandbox:network` violation. In-process
  tool modules are operator code and are not sandboxed.
- **Every decision is recorded.** `policy.decision` for all, `violation` for
  refusals, with severity, rule, tool, argument digest and policy version.
- **Instances have a lifecycle.** Created, running, finished, failed,
  cancelled, with a root directory, an event log and a timeout each.
- **Inputs are checked before the model is called.** A missing input fails in
  milliseconds, not after six turns.

## Evals

`mainsheet/evals/taxonomy.yaml` lists the misalignment categories every agent must be
tested against. The generator writes one case per category for a given agent,
with fixtures its tool adapters can plant and assertions on behaviour, output
and quality. Cases are proposals: a person reads, edits and commits them. Each
case runs several times and passes on a rate. Results append to
`evals/baseline.jsonl` with model and policy version, so a change in behaviour
is a diff between two rows.

## Layout

```
mainsheet/agent/        runtime: config, policy gate, instances, events, evidence, tools
mainsheet/panel/        FastAPI panel and the React Flow canvas
mainsheet/evals/        taxonomy, case schema, generator, runner
mainsheet/agent.yaml    the example agent
mainsheet/paths.py      the working folder and the shipped files
evals/suites/           eval suites for the example agents
tests/                  unit tests
docs/                   practices and the product proposal
```

## Status

Early. Single machine, in-memory registry, Apple Notes as the example tool.
See `docs/proposal.md` for where it goes and `docs/practices.md` for the rules
the code follows.

## License

AGPL-3.0-or-later.
