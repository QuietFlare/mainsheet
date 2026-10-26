# ADR 0005: An app extends the runtime with a pipeline, skills and a human

Status: accepted

## Context

Mainsheet runs one agent per instance, defined in one file, under a gate. ADR 0001 keeps orchestration out of the schema until it is added to the schema, and ADR 0004 declines an orchestrator altogether and defers to two tool servers.

A use case has now arrived from inside the project: a product build that runs as a chain of agents, interview, specification, build, validation, release, deployment, where every stage must run under the same gate and leave the same record, and where some stages need a person to answer questions or approve the result. Nothing outside Mainsheet is to run any part of it. Three things the runtime lacks stand in the way. There is no way to run agents in sequence and hand one agent's output to the next. There is no way to give an agent a method to follow beyond its prompt. And the only human path is a refusal: a tool marked `approval: human` is denied with the reason that no person is available.

The domain knowledge of such a build, the questions to ask, the templates, the reference stack, does not belong in a runtime whose purpose is a gate and a record.

## Decision

Mainsheet gets an extension point for apps, a pipeline file, skills on an agent, and a human the agent can address. The domain stays outside.

An app is a Python package that depends on Mainsheet and registers itself through an entry point group. It adds a subcommand to the `mainsheet` command and ships its own agent files, pipeline file, tool servers and skills. Mainsheet loads it and knows nothing of its domain. An app is operator code, trusted as tool modules are.

A pipeline is one file with its own schema: an ordered list of stages, each naming an agent file, the paths in the work folder it hands to the next stage, and whether a person must approve before the next stage starts. Stages run one after another, each as an instance of its own, and the pipeline has an instance id that every stage's record carries. One cost cap covers the pipeline and is drawn down by every stage, beside each stage's own cap. Taint carries from stage to stage as it carries across resumed runs. Every handoff is a record in the chain holding the digests of the files handed on, so the chain shows which output each stage was built from. There is no branching, no retry with logic and no message between agents; the channel server of ADR 0004 remains the only way two agents talk.

An agent file may name skills. A skill is a folder with a `SKILL.md`, shipped by an app and loaded through the harness as a local plugin, so it never has to be in the working folder. The skill's content is part of the definition digest: the same agent with a changed skill is a different agent. A skill is context the model reads, not a boundary; the gate enforces nothing written in it.

The human is one tool server that Mainsheet provides, `ask_human`, with one tool that puts a question and waits for the answer. The first backend is the terminal the run was started from; the panel is a later one. The tool is gated like any other, so the policy says which agent may ask and how often, and every question is a decision in the chain. `approval: human` becomes a real path: when a human backend is attached the gate puts the call to the person and records the answer, and when none is attached the call is denied as before. Time spent waiting for a person does not count toward the run timeout.

## Consequences

This supersedes the sentence of ADR 0004 that refuses an orchestrator. The rest of ADR 0004 stands: no swarm, memory and channel as tool servers, one agent by default.

Mainsheet stays a gate and a record. A pipeline adds order and handoff, nothing more, and the gate has no new rule kinds. A reviewer reads one more file.

An interview run is long and mostly idle. The schema's limits on turns and time were set for unattended runs and will be revisited for stages that wait on a person or build for hours; that is a separate decision.

Skills are visible to the model's file tools whatever the skill list says, so a skill holds no secret and no rule that should be enforced; rules go in the policy and in tool functions.

Two claims here were confirmed by a live run before this record was accepted, with `agents/human_probe.yaml`: a tool waiting on the terminal holds the harness for over a minute without a timeout of its own, and a plugin-shipped skill reaches the agent under the name the agent file gives and is invoked through a `Skill` call the gate decides on.

The app extension point and the pipeline file are decided here and built next; the human tool and skills are built.
