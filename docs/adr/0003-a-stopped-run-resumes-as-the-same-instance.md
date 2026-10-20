# ADR 0003: A stopped run resumes as the same instance

Status: accepted

## Context

A run that stops on a budget leaves its work on disk and its conversation in the harness session. Continuing it meant starting a new instance whose task told the model to read the previous output and carry on. The new run had no memory of what the previous one had read, repeated work, and its gate started clean although the previous run may have consumed untrusted output.

The harness can restore a session by id, which brings back the whole conversation. Mainsheet had not recorded that id.

## Decision

`mainsheet agent.yaml --resume <instance id>` continues an instance. It is the same instance: same id, same work folder, same event log, with a new `instance.resumed` record in the chain. The harness session id is read from the instance's log, or, for runs recorded before this change, from the harness's own transcript folder for the instance's work directory. Every run now logs its session id when the session starts and when it ends.

Three things carry over and one does not.

The conversation carries over, restored by the harness. The resumed run is given a short continuation prompt instead of the original task, because the restored conversation already holds the task and repeating it would start the work again.

The taint carries over. Before the first call, the gate replays the instance's earlier tool calls against the policy; if any of them had untrusted output, the gate starts tainted and irreversible tools stay denied. A fresh run must not launder what an earlier run read.

The cost accounting carries over in one direction. The harness reports the session's total cost, so a resumed run records its own cost as the difference from the previous total and the session total beside it.

The budget does not carry over. Tool-call and cost counters start fresh, which is the purpose of resuming.

## Consequences

An instance's log now spans several runs. Readers of the log, the verifier included, must treat `run.started` after `instance.resumed` as a new run of the same instance, not a new instance.

Resume depends on the harness's transcript. If the harness deletes or rotates a session, the instance cannot be resumed and the command says so.

A resumed run's working directory is unchanged, so file-path rules in the policy keep meaning what they meant.
