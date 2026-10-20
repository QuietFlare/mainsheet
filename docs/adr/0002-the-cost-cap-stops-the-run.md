# ADR 0002: The cost cap stops the run, enforced by the harness

Status: accepted

## Context

A policy carries two budgets: a maximum number of tool calls and a maximum cost in USD. The gate enforced the first before every call. The second was compared to the run's total only when the result message arrived, so a run could exceed its cost cap by several times and the breach appeared as a violation in the log after the money was spent.

The gate cannot enforce cost itself. It sees tool calls, not tokens, and the cost of a run accrues in model calls between tool calls. The harness that runs the model loop knows the cost after every call and accepts a budget as an option.

## Decision

The policy's cost cap is passed to the harness, which ends the run as soon as the cap is reached. Mainsheet records the stop as a `budget:cost_usd` violation, the same shape as a tool-call budget denial, and the run finishes rather than fails. The run's result message, when the harness produces one, is kept; the error the harness raises afterwards is swallowed only when its subtype says the stop was the budget. Every other error result still raises.

The comparison at the end of the run stays as a second check. It fires only when the total exceeds the cap without a harness stop, which would mean the harness did not honour the budget.

## Consequences

The cap is a brake, not a report. A run can overshoot by at most one model call, because the harness checks after each call. A cap set below the cost of the first call ends the run after it.

The tool-call budget stays in the gate. It is the one budget Mainsheet enforces itself, and the one that works when the harness does not report cost.

Budget enforcement is delegated to the harness. If the harness changes how it reports a budget stop, the subtype check in the runtime has to follow.
