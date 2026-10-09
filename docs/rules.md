# Rules

The non-negotiables a diagram cannot show. Drawn from the README's
guarantees and `practices.md`; a pull request that breaks one is reported,
never quietly accepted. Change a rule here first, then the code.

- The gate decides before every tool call, in code, in a PreToolUse hook.
  The model is asked what it wants, never whether it may.
- A refused call stays refused for the run. A retry gets no fresh decision.
- Every decision is recorded three ways: an event on disk, a span, and a
  signed receipt. Raw arguments are never stored, only a digest.
- Egress is a sandbox boundary, not a gate rule. A command reaches only
  the hosts in `policy.network.allow`; empty means none.
- The tool function is the security boundary. Every limit is enforced
  inside the function, never in the prompt.
- Tools are bound to one agent when built. A server started by command
  receives only the environment entries its definition names.
- One schema validates the agent file, the panel's API and the panel's
  form. The panel holds no state of its own.
- Inputs are validated before the first model call.
- Generated evals are proposals until a person renames them. The judge
  sees only the output, never the agent's context or tool calls.
