# ADR 0001: An agent is one file

Status: accepted

## Context

Agent frameworks define an agent in code: a class, a graph of nodes, decorators on functions. The model, the prompt, the tools and whatever guards exist are spread across the program that runs them. Two consequences follow. The definition cannot be reviewed without reading the program, and it cannot be fingerprinted, so a record that says "this agent ran" cannot say which agent.

Mainsheet's purpose is a record of what an agent did that stands on its own. That record has to name the definition it governed, and the definition has to be something a reviewer can read, diff and approve without running anything.

## Decision

An agent is one YAML file. It holds the model, the limits on turns and time, the system prompt, the task, the tools the agent may call and the policy on each call: allowed or not, approval required, irreversible, untrusted output, argument patterns, deny patterns, budgets and network egress. One schema validates the file, and the panel edits the same schema, so there is no second way to define an agent.

Tools come from one of two places. A Python module that exposes a `make_server` function, bound to one agent when it is built. Or a program Mainsheet starts and speaks MCP to, given as a command with arguments and an environment, where variables expand from the environment with optional defaults. The file names which of a server's tools the agent may use; a tool the file does not name is refused by the gate as unknown.

The whole file is fingerprinted. Its digest is written into the chain when an instance is created, so every decision record points at the exact definition that was in force.

## Consequences

Reviewing an agent is reading a file. Changing its policy is a diff. Two runs with the same digest ran the same agent.

The policy and the agent live together on purpose. A policy that lives apart from the agent it governs is applied by whoever remembers to; one that lives in the same file cannot be left out.

What the file cannot express, the runtime does not do. Orchestration between agents, conditional flows and retries with logic are not in the schema, and adding them means adding them to the schema first, where they can be reviewed like everything else.

Tool modules are operator code, loaded into the process, and are trusted as such. Command servers run as separate processes. The file does not distinguish the two in trust, only in how they are started.
