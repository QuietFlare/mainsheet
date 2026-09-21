# Mainsheet: product proposal

## The problem

Teams in regulated fields can build agents in an afternoon and cannot deploy
them, because nobody can answer two questions: what is this agent allowed to
do, and what did it actually do. Today the answers live in prose files the
model may or may not follow, in dashboards that can be edited, and in the
memory of whoever ran it.

The tooling market splits into three camps that do not meet. Frameworks and
visual builders make agents. Gateways enforce policy at the tool call.
Compliance platforms generate documents. None of them gives an engineer one
file that says what the agent may do, one record that proves what it did, and
one test suite that says how it behaves when the input is hostile.

## What Mainsheet is

An agents runtime. Define an agent in one file, run it governed, prove what
it did.

- **A runtime** that executes agent definitions with guarantees: a policy gate
  before every tool call, budgets for turns, calls, time and cost, tools bound
  to one agent, an append-only event log, OpenTelemetry traces, and an
  incident for every refusal.
- **A template** a new agent starts from: definition, policy table, tools, a
  generated and reviewed eval suite, tests and a README, produced by one
  command.
- **A workbench** to create, configure, connect, run and watch agents on a
  canvas, and to test them against a fixed taxonomy of misalignment.

## Who it is for

Platform and security engineers at companies that must show their work:
finance, health, life science, public sector. The first user is the engineer
asked to make an agent safe enough for a security review. The second is the
reviewer, who reads the policy table and the eval results instead of the code.

## Why now

Agent frameworks converged on the same loop in 2025. The Model Context
Protocol made tools portable. OpenTelemetry's GenAI conventions made traces
portable. The EU AI Act's logging duties applied in August 2026 and its
harmonised standards are unfinished, so every vendor logs what is convenient.
The pieces exist. The assembly that an engineer can read end to end does not.

## What exists, and how this differs

- **Vaara** gates tool calls and writes signed receipts. Mainsheet uses the
  same hook contract and will run Vaara as a second gate and its trail as the
  signed witness. Mainsheet adds the definition, the budgets, the instances,
  the evals and the workbench.
- **Langflow, Dify, Flowise, and the vendor builders** make agents on a canvas.
  Mainsheet's canvas is a view over files and its agents run under a gate;
  none of the builders has a policy table or a misalignment suite.
- **The OWASP Agentic Skills Top 10** defines the risks and a permission
  manifest with no enforcement. Mainsheet's gate implements three of its
  runtime controls and its eval taxonomy maps to its risk list.

## What is built

Runtime, gate with tests, instances, events and traces, the canvas, the eval
taxonomy, generator, lint and runner, with Apple Notes as the example tool. It
runs on one machine with your Claude login.

## What is next, in order

1. Persist the instance registry and add an executor interface: local process
   now, a scheduler or cloud task later.
2. Vaara as second gate and signed trail; Clew reading the trail for impact
   analysis and a remediation plan after an incident.
3. Human approval as a real path instead of a refusal.
4. The scaffold: `mainsheet create --name X` producing a self-contained agent
   project, and a container image as the deployment unit.
5. Identity per instance and a cloud reference deployment.

## Business

Open source under AGPL. Revenue from engagements: installing Mainsheet at a
client, writing their tools and policies, producing the eval suite and the
evidence a reviewer accepts. The product is the proof that the engineer can do
the work; the work is the product.

## Risks

- A framework vendor adds a policy table and evals to its builder.
  Mainsheet's answer is being neutral across harnesses and readable end to end.
- The policy gate cannot see intent. It bounds what an agent can do and
  records it; evals are the only lever on what it tries to do. The proposal
  claims containment and evidence, not alignment.
- One maintainer. Mitigated by keeping the runtime small and tested, and by
  building the rest on existing components.
