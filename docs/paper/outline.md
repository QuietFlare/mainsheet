# Outline: an experience report on Mainsheet

## Shape after the author's review, 2026-10-26

Title: Four lessons from governing an agent at the tool call.

The paper is framed as governance in three obligations, define, enforce,
prove, with the four lessons as where each turned out harder than the
design assumed, and a section mapping the three parts to AI Act Articles
12 and 14 and the OWASP agentic rows, with what is not covered. After an
external review on 2026-10-26 it gained a run table, a paragraph on what
the chain does and does not prove, the three cost figures told apart,
reversible versus safe, approval semantics, a conclusion, and softer
wording where two cases do not carry "every time". About 3,650 words
before references, which is over the venue's length and needs a cut
pass by the author. The gate-versus-prompt
headline is dropped: a code check beating a prompt on the author's own
nine cases shows nothing a reader does not already believe. The three-arm
benchmark stays in the repository, unrun, named in one paragraph of the
paper as the next step once it has cases somebody else wrote (InjecAgent).
Runs are named by letter in the paper, no project names, no toy tool
beyond the probe. Sections 3 and 4 of the plan below are superseded; the
rest still describes what each lesson rests on.

## The plan as first proposed

Working title, two options:

1. Rules in the gate hold where rules in the prompt do not
2. What held and what did not when an agent ran under a policy gate

Venue shape: IEEE Software experience report, 3,000 to 4,000 words in the
journal, longer on arXiv. One author. Practitioner reader. Every number in
the text points at a file in this repository at a named commit.

Code is cited at `main`, commit `0075744` (2026-10-26). The branch
`test/adr-0002-review` carries commit `443ff56`, which removes the harness
cost cap on purpose to test the design review workflow, so nothing is cited
from that branch.

## The headline claim and what stands behind it today

Claim: a rule enforced in code before each tool call holds whatever the
prompt says, and a rule written only in the prompt holds some of the time.

What exists for it:

- `bench/gate/`: three definitions of one agent (`arm_prompt.yaml`,
  `arm_gate.yaml`, `arm_both.yaml`), the nine-case suite
  `evals/suites/mainsheet.yaml`, a runner that tables the suite's verdict,
  harm and totals per arm, and a unit test on the runner
  (`tests/test_bench_gate.py`). The README says what the gate can and
  cannot catch, case by case.
- No results. `bench/gate/results/` does not exist and no `standup-*`
  instance exists under `instances/`. The comparison has been designed and
  not run. The three runs under `bench/` are the memory sharing benchmark
  (arm A, arm B, arm B staggered), a different question.

So the claim is today a hypothesis with a test built for it. The report
can go two ways, and the author decides: run the comparison before the
draft (81 runs, under five dollars, about an hour, Apple Notes open, from
her own terminal), or write the draft with the benchmark section stating
the design and the expected shape and no numbers. The outline below
assumes the first; the second only removes section 4's table.

## Sections

### 1. The question (about 300 words)

Teams can build an agent in an afternoon and cannot say what it may do or
what it did. The usual place for rules is the prompt, which the model may
or may not follow. The report asks where a rule has to live to hold, and
what a record of the run has to contain to answer the second question.

Evidence: `docs/proposal.md` (the problem statement), `README.md` lines
3 to 14.

### 2. Mainsheet in one page (about 500 words, one figure)

One YAML file is the agent: model, prompt, task, tools, policy. A gate in
a PreToolUse hook decides before every call under rules the model never
sees. Every decision is an event on disk and a signed receipt in a hash
chain; `mainsheet-verify` checks both. Budgets on calls, cost, turns and
time. Egress is a sandbox boundary, not a rule. An eval suite per agent,
generated and then reviewed by a person. Built on the Claude Agent SDK.

Evidence:

- `mainsheet/agent/policy.py`: the gate and its eleven rule names
  (`denial_continuity`, `unknown_tool`, `tool_not_allowed`, `arg:<name>`,
  `pattern:<regex>`, `tainted_irreversible`, `approval_required`,
  `budget:tool_calls`, `approval:human`, `sandbox:network`, and
  `budget:cost_usd` in `runtime.py`).
- `mainsheet/agent/evidence.py`: receipts through Vaara's chain, the
  verifier.
- `mainsheet/agent/config.py`: the digest covers the file and the skills;
  `sandbox_settings()`; `setting_sources=[]`.
- `docs/adr/0001` (one file), `docs/practices.md`, `docs/rules.md`.
- Figure: `docs/mainsheet.png`, or a simpler flow drawn for the paper.
- A verified run as the worked example: `instances/human_probe-1fcba1f5`,
  two decisions, 2/2 receipts verify, chain shown by `mainsheet-verify`.

### 3. What a gate can see (about 400 words, one table)

The gate sees tool names and arguments. It cannot see what the agent
writes inside an allowed call. The suite's nine cases split along that
line, and the report says so before any result: injection and forbidden
tool are tool-shaped and the gate can catch them, scope creep, sensitive
data, contradiction and ambiguity are text-shaped and it cannot, budget is
partly caught, missing input is caught by preflight in every arm.

Evidence: the table in `bench/gate/README.md`, the cases in
`evals/suites/mainsheet.yaml`, the categories in
`mainsheet/evals/taxonomy.yaml`.

### 4. Prompt, gate or both (about 600 words, two tables)

Same model (Sonnet 5.5), task, tools, cost cap. Arm prompt: every rule in
the system prompt, no argument pattern, no deny pattern, a 50-call budget.
Arm gate: one line of prompt, the title pattern `^Standup`, the shell deny
pattern, ten calls. Arm both. Three repeats per case, 27 runs per arm. The
suite's assertions decide; the runner adds one derived column, harm.

Result tables from `bench/gate/results/gate-<stamp>.md` once the run
exists, with the definition digests from the JSONL beside them. The
reading the README predicts: the gate holds on the tool-shaped rows
whatever the prompt says, the prompt holds or fails on the text-shaped
rows, and the third arm shows whether the two add up. The paper reports
what the tables say, including where the prediction was wrong.

One honest note that belongs here: the `forbidden_tool` case requires a
violation, so the prompt arm fails it by construction even when the agent
declined on its own. The harm column is the fair comparison there.

### 5. Four lessons, each from one run (about 1,200 words)

Each lesson: the event, the log line, the change, the decision record.

**5.1 A cost cap checked at run end is a report, not a brake.**
Run `aurae-research-26c87720`, 2026-10-20, a 16-question desk research
job billed to an API key. 94 calls attempted in the first run, 90 allowed,
four refused by the gate (two `Read` outside the path pattern, one
`WebFetch` and one `Write` at the 90-call budget). Cost 7.0905 USD against
a cap of 2.0, logged as a violation at 11:59:46, after the money was
spent. The fix: the cap is handed to the harness. Run
`aurae-research-3d062e9f` the same afternoon, cap 0.10, stopped by the
harness at 0.104129 after two calls, `run.stopped` in the log, 2/2
receipts verify. ADR 0002. Overshoot is at most one model call.

Files: `instances/aurae-research-26c87720/events.jsonl` (violations at
11:46:49, 11:47:14, 11:57:19, 11:58:58, 11:59:46 local time; `run.ended`
turns 139, cost_usd 7.0904795), `instances/aurae-research-3d062e9f/
events.jsonl`, `docs/adr/0002-the-cost-cap-stops-the-run.md`,
`evolution/aurae/research-agent.yaml` (the definition, outside this repo),
`agents/capped.yaml` (the 0.10 variant).

Also from this run, for section 2 or a sidebar: resumed at 13:57 with
`tainted: true` carried from the first run, ten more calls, 104/104
receipts verify across both runs. And one defect the log keeps: the resumed
run logged "8.7193 exceeded 2.0 without a harness stop" because the
harness reports session totals and the delta fix came afterwards. The
paper says so rather than cleaning it.

**5.2 A binary taint bit makes the operator weaken the policy.**
The rule: an irreversible tool is refused for the rest of the run once any
tool marked `untrusted_output` has returned. A research agent reads the web
and then writes a file, so under the rule it can never write. Two agent
files mark their writes reversible to get past it:
`evolution/aurae/research-agent.yaml` (`Write: irreversible: false`,
`WebSearch` and `WebFetch` untrusted) and a second one with untrusted
`Bash` and a reversible `Write`, not named in the paper. The benchmark has no taint arm for
the same reason (`bench/gate/README.md`, last paragraph). The lesson: a
taint that is binary and run-wide pushes the operator to mark the
dangerous tool safe, which is the opposite of what the rule is for. What
would fix it (per-argument taint, or taint that clears on a reviewed
write) is named as not built.

Files: the two YAML files above, `mainsheet/agent/policy.py` lines on
`tainted_irreversible`, `docs/adr/0003` (taint carried across resume).

**5.3 Two permission layers can disagree.** Needs a decision, see below.
The runtime sits on a harness with its own permission system (permission
mode, allowed tools, sandbox, settings sources). What is logged:

- On 2026-10-20 the harness loaded the operator's own assistant settings
  into the research run. The model's second call was a `Read` of a private
  file of the operator's that those settings name. The gate refused it
  (`arg:file_path`, 11:46:49) and the run went on. The fix on 2026-10-26:
  `setting_sources=[]` in `config.py`, so nothing of the operator's own
  configuration reaches a run.
- A refusal reaches the model as the harness's hook error text
  (`PreToolUse:Read hook error: ...`), seen in the harness transcript of
  `aurae-decision-record-a7d7e75c`. The agent then asked the person for the
  file names it could not list. A refusal the model can read is a refusal
  it can work around honestly.

What is not logged: the claim that a `Write` the gate allowed was refused
by the harness outside the instance's work folder. It appears as a comment
in `aurae/agents/decision_record.yaml` and in a session note, and in no
`events.jsonl` or harness transcript. Either it is reframed to the two
logged events above, or a ten-cent probe is run to produce the log before
the draft.

**5.4 A person's answer is a gate decision, and their time is not the
run's.** `approval: human` was a refusal with the reason that nobody was
there. Now one backend per process, attached by the command that started
the run, answers both the agent's questions and the gate's approval
prompts, and the time spent waiting is subtracted from the run clock.

Run `human_probe-1fcba1f5`, 2026-10-26: `timeout_s: 60`, `ask_human`
called 09:03:07, answered 09:04:15 (68 seconds waiting), run finished at
09:04:18 after 77 seconds, cost 0.035026 USD, 2/2 receipts verify. Run
`aurae-decision-record-fd147e2f` the same morning: a plugin skill invoked
through a gated `Skill` call, three reads, four questions to the author
with answers taking 43, 35 and 39 seconds, cancelled by her during the
fourth. The approval path on `Write` was not reached in that run and the
paper says so.

Files: `instances/human_probe-1fcba1f5/events.jsonl`,
`instances/aurae-decision-record-fd147e2f/events.jsonl`,
`instances/aurae-decision-record-a7d7e75c/events.jsonl`,
`agents/human_probe.yaml`, `aurae/agents/decision_record.yaml`,
`mainsheet/agent/tools/human.py`, `runtime.py` `bounded()`,
`docs/adr/0005`.

### 6. Related work, placed honestly (about 400 words)

What this report is not: not a benchmark paper, not a defence against
prompt injection, not an alignment claim. The gate bounds what the agent
can do and records it. Four groups, each with what Mainsheet takes from it
and what it does not do:

- Agent security benchmarks: AgentDojo, InjecAgent, Agent Security Bench.
  They measure attacks; this report measures one runtime on its own nine
  cases and plans to borrow their cases (section 8).
- Agent task benchmarks: tau-bench. Rules written as policy documents the
  agent must follow in conversation, which is the prompt arm's premise at
  scale.
- Guardrail frameworks: NeMo Guardrails, Guardrails AI, Llama Guard.
  Checks on text in and out; Mainsheet checks tool calls, and has no output
  gate yet (`docs/owasp-plan.md` step 3).
- Design approaches: CaMeL and the design patterns paper of Beurer-Kellner
  and others, which also move the rule out of the model's reach. Harness
  permission systems (Claude Code hooks and sandbox, OpenAI Agents SDK
  guardrails) are the layer Mainsheet sits on, and section 5.3 is about
  that seam.
- Evidence and oversight: METR's reports (long-task horizon, the
  multi-agent evaluation that ADR 0004 cites), OWASP Agentic Top 10, EU AI
  Act Articles 12 and 14, OpenTelemetry GenAI conventions, MCP.

Citations are checked against the papers before the draft is called done.

### 7. Limitations, stated plainly (about 300 words)

One operator, who also wrote the runtime, the cases and the policies. Own
cases: nine, own taxonomy, one toy tool (Apple Notes). One model family,
two versions (Sonnet 5 and 5.5). One machine, an in-memory registry. Small
numbers: three repeats, four real runs. The runtime depends on one harness
and on how it reports cost and budget stops. The turn count in the log
counts assistant messages, not harness turns (139 against a limit of 50).
The cost figures are the harness's price table. One false violation stands
in a log. The gate cannot see intent or text.

### 8. Future work (about 200 words)

InjecAgent cases fed into `bench/gate` as a fourth source of cases,
planned as a separate step after this draft. A small study with other
operators writing policies for the same agent, to find out whether the
taint and pattern rules are usable by someone who did not write them. An
output gate. Filesystem limits in the policy.

### 9. Reproduce it (about 150 words, one block)

Commit, `pip install`, the three commands (`mainsheet`, `mainsheet-verify`,
`bench/gate/run.py`), the instance ids named in the text, and where
`instances/` and `trail/` are in the repository.

## The runs behind the paper

The paper names runs by letter so no project name appears in the text.

| letter | instance | date | what it is |
|---|---|---|---|
| A | `aurae-research-26c87720` | 2026-10-20 | desk research, 16 questions, 2.00 cap, API key, resumed at 11:57 UTC |
| B | `aurae-research-3d062e9f` | 2026-10-20 | same agent, 0.10 cap, stopped by the harness |
| C | `human_probe-1fcba1f5` | 2026-10-26 | probe for the human path, 60 s timeout |
| D | `aurae-decision-record-fd147e2f` | 2026-10-26 | interview agent, four questions, cancelled |
| D' | `aurae-decision-record-a7d7e75c` | 2026-10-26 | first attempt of D, folder listing refused, agent asked the person |

The paper's run D covers both D and D': the refused listing is from D',
the four questions from D. The data folder should carry both.

## Where each number in the paper comes from

Times in the paper are UTC. `events.jsonl` stores epoch seconds; the
receipts and `mainsheet-verify` print UTC.

| number | file |
|---|---|
| first commit 21 September 2026 | `git log`, commit `5edd3ad` |
| gate rules | `mainsheet/agent/policy.py` (`Gate.pre`, `Gate.approved`, `Gate.post`), `runtime.py` (`budget:cost_usd`) |
| nine cases | `evals/suites/mainsheet.yaml`; categories in `mainsheet/evals/taxonomy.yaml` |
| Table 1 | `bench/gate/README.md` |
| three arms, 50 and 10 calls, `^Standup`, 0.50 USD | `bench/gate/arm_prompt.yaml`, `arm_gate.yaml`, `arm_both.yaml` |
| 27 runs per arm, 81 in all, Sonnet 5.5, Haiku 4.5 judge | `bench/gate/README.md`, `mainsheet/evals/run.py` (`judge`) |
| benchmark tables | `bench/gate/results/` (pending) |
| A: 94 attempted, 90 allowed, 4 refused | `instances/aurae-research-26c87720/events.jsonl`, events before `instance.resumed` |
| A: 7.0905 USD against 2.00, ended 09:59:46 UTC, 139 turns | same file, `violation` and `run.ended` at ts 1792490386 |
| A: 90-call budget, 2.00 cap, path patterns | `agents/capped.yaml` is the run's definition with the cap changed to 0.10, nothing else |
| A: resumed, tainted, 10 calls, 104 of 104 receipts | same file after `instance.resumed`; `mainsheet-verify aurae-research-26c87720` |
| A: wrong line 8.7193 | same file, `violation` at ts 1792497589 |
| A: private file read refused at 09:46:49 UTC, second call | same file, `violation` at ts 1792489609 |
| B: 0.104 USD on a 0.10 cap, two calls, six seconds, 2 of 2 receipts | `instances/aurae-research-3d062e9f/events.jsonl`, ts 1792496029 to 1792496036 |
| empty setting sources | `mainsheet/agent/config.py`, `build_options`, `setting_sources=[]` |
| second agent with untrusted Bash and reversible Write | an agent file under `agents/`, gitignored, not named in the paper |
| no taint arm | `bench/gate/README.md`, last paragraph |
| D': folder listing refused, then a question | `instances/aurae-decision-record-a7d7e75c/events.jsonl`, ts 1792006090 and 1792006094; the hook error text is in the harness transcript |
| C: 60 s timeout, 68 s wait, 77 s run, 0.035 USD, 2 of 2 receipts | `agents/human_probe.yaml`; `instances/human_probe-1fcba1f5/events.jsonl`, ts 1793001781 to 1793001858 |
| D: four questions, 43, 35 and 40 s (42.6, 35.0, 39.8), cancelled, 8 of 8 receipts | `instances/aurae-decision-record-fd147e2f/events.jsonl`, `tool.called` and `tool.returned` pairs |
| receipts carry no argument digest; the log's decision event does | `mainsheet/agent/evidence.py` (`record`, the digest goes into the request context), one receipt file |
| the call event holds the arguments | any `events.jsonl`, `tool.called` `input`; `docs/rules.md` says raw arguments are never stored, which holds for receipts and not for the log |
| approval only on a plain yes, wait subtracted | `mainsheet/agent/policy.py` (`Gate.approved`), `runtime.py` (`bounded`), `tools/human.py` |
| decision records | `docs/adr/0001` to `0005` |
| Vaara 2.5.0, Claude Agent SDK 0.2.157 | installed package metadata, `pyproject.toml` |

## Data folder to assemble, for the author's review

Assembled on 2026-10-26 under `docs/paper/data/`, 137 files, 836 KB:
one folder per run (A, B, C, D, D-first) with `events.jsonl`, the
receipts, the definition and plugin, plus `issuer-es256.pub.pem`,
`verify.py` and a README. `python docs/paper/data/verify.py` reports
120 of 120 receipts verifying against the key alone. `docs/paper/data`
is not gitignored, so committing `docs/paper` publishes it.

Redacted on the author's word on 2026-10-26, as the data README states.
Before that, the review list was the following. Run A's log holds every search query,
every fetched URL (39 hosts, mostly KBV, CGM, EU health pages), the path
of the refused private file, and the operator's home path in file
arguments. The home path also appears in B, D and D-first logs, in one
D-first receipt (the refusal reason carries the path pattern), and in
the three definitions. Run D's log holds the four questions, which
restate the author's design notes. The person's answers are not logged.
Instance ids and definitions carry the project name, which the paper's
text does not.

## Decisions for the author before drafting

1. Run `bench/gate` before the draft, or draft without its numbers.
2. Lesson 5.3: reframe to the two logged events, or run a probe for the
   harness-refused write first, or both.
3. Whether the private-file read in 5.3 is described as "a private file of
   the operator's, named in the operator's own assistant settings", or left
   out.
4. Title, 1 or 2.
