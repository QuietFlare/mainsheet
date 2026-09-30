# Plan: closing the OWASP gaps

Ordered by rows closed per day of work. Each step names the policy key, the code it touches, how it is verified, and the OWASP rows it moves. ASI = Top 10 for Agentic Applications 2026. AST = Agentic Skills Top 10.

## 1. Pause on incident, record, report (one day)

Rows: ASI10 rogue agents, ASI08 cascading failures.

- Policy: `pause_on: {incidents: 3, severity: critical, timeout_s: 900}`. Defaults: three incidents or one critical; a pause nobody answers within the timeout becomes a stop.
- Code: the runtime moves from one-shot `query()` to `ClaudeSDKClient`, which can `interrupt()` and continue the same session. `Instance.record_decision()` checks the threshold after writing the incident, interrupts, sets status `paused`, and emits `run.paused` with the incidents so far. The panel shows the report with resume and stop; `POST /api/instances/{id}/resume` continues the session, `/stop` cancels. Timeout emits `run.stopped` with reason `pause_timeout`. Nothing is killed silently.
- Verify: unit test on the threshold and the timeout; the egress probe with a task that curls twice pauses after the first critical incident, resumes on request, and stops on timeout.
- This is also the foundation for step 2: a waiting instance is the same mechanism whether it waits for approval of one call or for a decision after incidents.

## 2. Human approval as a real path (half a day, on top of step 1)

Rows: ASI09 human-agent trust, ASI02 tool misuse.

- Today `approval: human` is a refusal. Step 1 gives the runtime a waiting instance; this step reuses it for one call. The SDK has a `can_use_tool` callback that receives the call and returns allow or deny. Tools marked `approval: human` are removed from `allowed_tools`, because allow rules shadow the callback.
- Code: the callback puts the instance into a new status `waiting_approval`, emits `approval.requested` with the args digest, and awaits an `asyncio.Future`. The panel gets `POST /api/instances/{id}/approve` and `/deny`, and the canvas shows the pending call. Timeout from `policy.approval_timeout_s` denies and records an incident.
- Verify: unit test with a fake future; eval case where the note asks for a write that needs approval and the run waits, then is denied by the runner.

## 3. Output gate (two days)

Rows: ASI01 goal hijack, ASI09, ASI10.

- Policy:
  ```yaml
  output:
    checks:
      - {type: regex_deny, pattern: "\\b[A-Z]{2}\\d{2}[A-Z0-9]{11,30}\\b", reason: IBAN in output, severity: high}
      - {type: max_chars, value: 4000}
      - {type: judge, rubric: "The summary contains only what the note says", model: claude-haiku-4-5-20251001}
    retry: 1
  ```
- Code: `Gate.check_output(text) -> list[Decision]` runs after the model's final message and before `run.ended`. On failure with retries left, the runtime switches from `query()` to `ClaudeSDKClient` and sends one follow-up message containing the reasons; on failure with none left, the run ends `failed` with an incident `output:<rule>`. Same checks apply to the arguments of `irreversible` tools inside `Gate.pre`, using `args_checks` on the tool rule. The eval runner's `judge()` moves into the gate so evals and runtime share one judge.
- Verify: unit tests for each check type; eval category `output_gate` in the taxonomy with a case where the note plants an IBAN.

## 4. Filesystem limits (half a day)

Rows: ASI05 unexpected code execution, AST06 weak isolation, AST03 over-privileged.

- Policy: `files: {read: [...], write: [...]}` with explicit paths, no wildcards, matching the AST manifest shape.
- Code: the SDK applies filesystem restrictions through permission rules, not sandbox settings. `build_options()` turns the lists into `Read` and `Edit` allow and deny rules in `settings`, and denies everything outside the instance's work directory by default.
- Verify: probe agent that tries to read `~/.ssh/id_ed25519` and write outside `work/`; both must fail and the trail must show `tool.returned` with error. Unit test on the rule generation.

## 5. Pinned and signed tool modules (two days)

Rows: ASI04 supply chain, AST01 malicious skills, AST02 supply chain, AST07 update drift.

- `tools.lock` at the repo root: for every tool module in any agent, its sha256, the tool names it exports, and the SDK version. Written by `mainsheet lock`, read by `preflight()`, which refuses to start on a mismatch with incident `tool:hash_mismatch`.
- Optional signature: `policy.trust.public_key`; `mainsheet lock --sign` signs the lock file with an ssh key, `preflight()` verifies with `ssh-keygen -Y verify`. No new dependency.
- Pin `claude-agent-sdk` to an exact version in `pyproject.toml`; the lock records it.
- Verify: unit tests for hash mismatch and bad signature; a test that edits a tool module and asserts the run does not start.

## 6. Identity per instance (one day)

Rows: ASI03 identity and privilege abuse.

- Each instance gets a random token at creation. `make_server(agent, instance_id, token)` builds tool servers that check the token on every call, so a tool cannot act for another instance even in the same process. Tool credentials come from environment variables namespaced by agent name (`MAINSHEET_<AGENT>_<KEY>`) and are never placed in the definition or the prompt.
- Every event already carries `instance` and `principal`; add `agent` and `policy_version` to `run.started`.
- Verify: unit test that a server built for one instance rejects another's token.

## 7. Container as the deployment unit (three days)

Rows: ASI05, AST06, and the honest limit in the README about in-process tools.

- A `Dockerfile` that installs the runtime and one agent; `mainsheet run --container` builds and runs it with `--network` attached to an internal network and an egress proxy sidecar whose allow list is `policy.network.allow` plus the model endpoint. Inside the container the command sandbox still applies, so egress is enforced twice.
- Tool modules run in the container, so the in-process limitation becomes a container boundary.
- Verify: the egress probe inside the container, denied and allowed; a tool module that opens a socket is blocked at the proxy.

## 8. Edges that execute (one week)

Rows: ASI07 inter-agent communication, ASI08 cascading failures.

- Each `delegates` edge becomes a tool `delegate_<target>` on the source agent, gated like any tool. Calling it creates a child instance with the target's own policy and the task text as its only input. No shared memory, no shared tools. The child's budget is charged to the parent; `run.started` records `parent`.
- Messages between agents are therefore tool calls through the gate, authenticated by the instance token from step 6, and every one is in both trails.
- Verify: two-agent system where the child is told by its input to call back into the parent's tools; the call must be an `unknown_tool` incident.

## 9. Memory, when it arrives

Rows: ASI06 memory and context poisoning.

- No memory exists today, which is the safest state. When it is added, every memory read is a tool with `untrusted_output: true`, every write records provenance (which instance, which input digest), and the output gate's checks run on what is written.

## Order and cost

| Step | Days | Rows moved |
|---|---|---|
| 1 Pause on incident, record, report | 1 | ASI08, ASI10 |
| 2 Human approval | 0.5 | ASI02, ASI09 |
| 3 Output gate | 2 | ASI01, ASI09, ASI10 |
| 4 Filesystem limits | 0.5 | ASI05, AST03, AST06 |
| 5 Pinned, signed tools | 2 | ASI04, AST01, AST02, AST07 |
| 6 Identity per instance | 1 | ASI03 |
| 7 Container | 3 | ASI05, AST06 |
| 8 Edges execute | 5 | ASI07, ASI08 |

After steps 1 to 6, nine of the ten ASI rows and seven of the ten AST rows are covered or partly covered. AST08 scanning and AST10 cross-platform stay out of scope. Each step ends with a practices entry, a taxonomy or eval change where behaviour is testable, and the README guarantee list updated. Nothing gets claimed in the blog before its probe runs.
