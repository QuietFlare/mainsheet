# Four lessons from governing an agent at the tool call

An experience report

Seema Jagadeesh, QuietFlare

Code at Mainsheet commit `0075744` on `main`.

## Abstract

Governing an agent means answering two questions. What was it allowed to
do, and what did it do. Mainsheet, a runtime on the Claude Agent SDK,
answers them with a policy in one file a reviewer can read and diff, a
gate in code that enforces it before every tool call, and a signed
receipt per decision an auditor can verify. Over five weeks I governed my
own agents this way, and four things happened the design had not
anticipated. A cost control checked at the end of a run is a report, not
a control. A control too blunt gets switched off by the operator it
protects. The runtime and the harness beneath it can disagree. Human
oversight must be a recorded decision, and the person's time is not the
agent's. The logs ship with the paper. The evidence is one operator, and
the report claims nothing beyond it.

## 1. What governing an agent means here

A team in a regulated industry can build an agent in an afternoon and
cannot deploy it, because nobody can answer two questions.

What is this agent allowed to do?

What did it actually do?

The first is the reviewer's question, asked before a deployment is
approved. The second is the auditor's, asked afterwards, often by the
same person. Today the first answer lives in a prompt the model may or
may not follow, and the second in a dashboard someone can edit, or in the
memory of whoever ran it. Neither survives the next question, which is
how do you know.

Mainsheet treats governance as three obligations on the runtime. To
define is to keep the policy as a document apart from the prompt,
versioned, fingerprinted, reviewable without running anything. To
enforce is to apply the policy in code at the point where the agent
touches the world, the tool call, under rules the model never sees. To
prove is to record every decision as evidence, so that an auditor who was
not there can verify what was allowed, what was refused and why, and that
nothing was altered afterwards. The policy,
the gate and the record are the three parts, and the rest of the runtime
exists to serve them.

A gate of this kind governs actions, not text. It sees a tool name and its
arguments and cannot see what the agent writes inside a call it allows,
so a phone number copied into a summary or a contradiction resolved
silently passes it. This report does not argue that such a gate makes an
agent safe. It reports what governing agents this way looked like in
practice, and where the three obligations turned out to be harder than
the design assumed.

## 2. Define, enforce, prove

Mainsheet is a Python package, first committed on 21 September 2026. It
runs one agent per instance on the SDK's agent loop.

**Define.** One YAML file is the agent, and the policy lives inside it,
because a policy kept apart from the agent it governs is applied by
whoever remembers to. The file holds the model, the limits on turns and
time, the prompt, the task, the tools, and a rule per tool. A rule says
whether the tool is allowed, needs approval, is irreversible, or returns
untrusted output, and gives a regular expression per argument. The policy
also carries deny patterns, a budget of calls and one of cost, and the
hosts commands may reach, none by default. Changing the policy is a diff.
The file is fingerprinted and the digest goes into the chain when an
instance is created, so every decision points at the exact policy in
force. Two runs with the same digest ran the same definition, which says
nothing about the model's output that day or the harness beneath it.

**Enforce.** A PreToolUse hook puts every call to a gate holding the
policy and the run's state. The gate refuses a tool not in the policy, an
argument outside its pattern, a string matching a deny pattern, an
irreversible tool after untrusted output, a tool needing approval with
nobody attached, and any tool once the call budget is spent. A refused
call, the same tool with the same arguments, stays refused for the run,
so a retry cannot wear the gate down. The run goes on and every other
call is decided on its own. The reason reaches the model as text. What a
command does once allowed happens inside that one decision. Egress is
enforced a layer down, because a rule can be retried and a closed socket
cannot. The policy's host list goes to the SDK's sandbox [7], which
denies every other host to every command. Budgets on calls, cost, turns
and time bound what a run can consume.

**Prove.** Every decision is recorded twice. Each tool call goes into the
instance's event log with its arguments, and each gate decision goes in
beside it with the tool, the rule, the verdict, a digest of the arguments
and the id of its receipt. The receipt is written through Vaara [8], a
library that keeps a hash-chained audit trail and signs one per decision.
It carries the decision, the tool, the agent and the time, not the
arguments or their digest. The instance's lifecycle goes into the same
chain, so a run reads as one sequence from the policy's digest to the
last decision. The verifier checks the chain and each receipt and
confirms that every decision event names a receipt that agrees with it.
The design decisions behind the runtime are kept as numbered records in
the repository.

What the chain proves is narrower than the word suggests. A verified
chain shows that each decision was signed at the time by the key the
runtime holds, that each receipt matches its event, and that nothing was
altered or removed afterwards without the verifier noticing. That is
detection, not prevention. The key sits on the same machine as the
runtime, so the receipts are the operator's own word made tamper-evident,
and someone with the machine and the key could rewrite the chain from the
start. The chain does not show that every event was captured, since a
decision never recorded leaves no gap, and it does not show what a tool
did once allowed. The receipt attests that a decision was made, and the
log, through the argument digest on the decision event, attests what it
was about. Several instances in one folder write to one chain, and the
runtime refuses to append to a chain already broken.

## 3. Four lessons, each from one run

The lessons came from runs on my own work, where I wrote the policy in a
hurry for a job I needed done. They were not chosen to test anything. I
read their logs afterwards and kept what the design had not foreseen.
Each lesson names the run by a letter, quotes the log, and names the
change. Table 1 lists the runs. Run A carries three of the four lessons,
so the runs are not one piece of evidence each.

Table 1. The four runs.

| run | date | what it was | control in question | what the log shows | what changed |
|---|---|---|---|---|---|
| A | 20 Oct | desk research, 16 questions, 90-call budget, 2.00 USD cap, resumed once | cost cap, taint, path pattern | 94 calls, 4 refused, 7.09 USD recorded at the end, a private file read refused, writes marked reversible | cap handed to the harness, settings kept out of runs |
| B | 20 Oct | run A's agent, cap 0.10 USD | cost cap in the harness | stopped at 0.104 USD after two calls | none, the fix held |
| C | 26 Oct | probe, 60 s timeout | human wait against the run clock | answer after 68 s, run finished at 77 s | none, the design held |
| D | 26 Oct | interview agent writing a design record, two attempts logged as two instances | path pattern, human questions, approval on write | first attempt, a folder listing refused and the agent asked instead; second attempt, four questions answered, canceled before the write | none, the approval path not reached |

Of what follows, the cost stop, the taint rule and its carry-over across
a resumed run, the approval semantics, the wait not counting against the
timeout, and the receipts failing when altered are each also covered by
a test in the repository. The claim that operators weaken a blunt taint
rule rests on two cases. Per-argument taint is a proposal.

### 3.1 A cost cap checked at run end is a report, not a brake

Run A, 20 October, was a desk research job of sixteen questions, billed
to an API key. The agent had read, search, fetch and write tools, path
patterns on read and write, a budget of ninety calls and a cost cap of
2.00 USD. It attempted 94 calls. The gate allowed 90 and refused four, two
reads outside the path pattern and then a fetch and a write at the
budget. The model's last message says the final write failed on the
budget and lists what was saved. The gate did what it was written to do.

The cost did not. The run ended thirteen minutes in with 7.09 USD
recorded, and one line before it a violation reading "run cost 7.0905
exceeded 2.0". The cap had been compared to the total only when the
result arrived. The gate cannot enforce cost. It sees tool calls, not
tokens, and the money accrues in the model calls between them. The
harness knows the cost after every call and accepts a budget as an
option, and the runtime had not passed it. The fix hands the cap to the
harness, which ends the run when it is reached, and records the stop as a
cost budget violation in the same shape as a call denial. Run B, the same
agent that afternoon with the cap at 0.10 USD, made two calls and was
stopped at 0.104 USD after six seconds. Both receipts verify. The harness
checks after each model call, so the overshoot should be at most one
call, and here it was. That bound is the harness's, observed once, not
proven by the runtime.

A run's record holds three cost figures. The cap is the policy's number.
The stop is the harness's act at its own price table. The recorded cost
is what the harness reported at the end, and for a resumed run the
harness reports the whole session, so the runtime records the difference
from what the session had cost before. That subtraction came after run A
was resumed, which is why one wrong line stands in its log (section 4).

### 3.2 A binary taint bit makes the operator weaken the policy

The taint rule is the gate's answer to indirect prompt injection. Once
any tool marked untrusted has returned, every tool marked irreversible is
refused for the rest of the run. The agent cannot read a web page and
then act on the world.

Run A's agent reads the web and then writes a file, so under the rule it
can never write. Its definition marks search and fetch untrusted and
marks write as reversible. A second agent of mine that runs a shell
command with untrusted output and then writes files does the same. Each
choice is defensible on its own, since a findings file in the instance's
own folder is reversible in the ordinary sense. The pattern is the
lesson. A taint that is one bit for the whole run gives the operator two
options, no writes or writes marked safe, and in both observed cases the
operator picked the second. The rule meant to stop a tainted write ends
up marking the write safe in advance.

Reversible is not the same as safe. A write into the instance's own
folder can still carry data out of a fetched page, or leave a file a
later run acts on, and marking it reversible only tells the taint rule to
look away. What the rule would need to track is which argument carries
untrusted content and where it goes, and what a reviewed write would
clear. Per-argument taint and a reviewed declassification are proposals
here, not solutions, and neither is built.

### 3.3 Two permission layers can disagree

The runtime sits on a harness with a permission system of its own, made
of a permission mode, an allowed-tools list, a sandbox, and settings it
loads from the operator's machine. Two events in the logs show the seam,
and they are two different failures. The first is configuration from
outside the definition leaking into a run. The second is the two layers
deciding the same call.

In run A, the agent's second call, four seconds in, was a read of a
private file of the operator's, named in the operator's own assistant
settings, which the harness had loaded into the run. The gate refused it
under the path pattern and the agent went on. The policy held, but the
rule that held was written for a different purpose, and nothing in the
definition had asked for the operator's settings to be in the run at all.
The fix for this first failure passes an empty list of setting sources to
the harness, so a run discovers only what its definition ships.

In the first attempt at run D, 26 October, logged as an instance of its
own, an agent allowed to read three named files tried to list their
folder instead. The gate refused, the harness passed the
refusal to the model as a hook error carrying the gate's reason, and the
agent's next call was a question to the person at the terminal asking for
the file names. A refusal the model can read is a refusal it can work
around honestly. This second seam has no fix, only a rule. The gate
decides, the harness still has a say, since a call the gate allows can
still fall to the harness's own permission mode, and the record has to
show both layers. Today it shows the gate's decision and, when the model
repeats it, the harness's refusal text, and no more.

### 3.4 A person's answer is a gate decision, and their time is not the run's

Until 26 October a tool marked for human approval was refused with the
reason that nobody was available. Approval was a rule the gate could
state and not grant. The change is one backend per process, attached by
the command that started the run. A tool `ask_human` puts the agent's
question and returns the person's line. The gate puts an approval to the
same person and records their yes or no as the decision, with their words
as the reason. The answer is trimmed and lowercased, and only y or yes
allows. Any other answer, a closed terminal, or nobody attached is a
denial bound to that tool and that argument digest, and it stays for the
run. The question has no timeout of its own, because the run clock stands
still while it is open, and canceling the run ends the wait.

Run C, a probe with a sixty-second timeout on purpose, called `ask_human`
six seconds in and got its answer 68 seconds later. The run finished 77
seconds after it started, without a timeout, at 0.035 USD. Run D, the real job, put four questions to me, answered in 43,
35 and 40 seconds before I canceled during the fourth. All eight of its
calls were allowed and verify. Its final write, marked for approval, was
not reached, so the approval path is proven in tests and not yet seen on
a real job.

## 4. What this governs, and what it does not

Two external texts shaped the three obligations, and neither is satisfied
by them. The EU AI Act's Article 12 [10] asks for automatic recording of
events over a high-risk system's life, and Article 14 for effective human
oversight. The chain and the approval path were built with those two in
mind. The chain records every gate decision and every lifecycle step,
with the policy's digest, and nothing else. The agent's work files, the
harness transcript and the definition file itself are outside it. The
approval path, the question tool and the cost stop exist since 26 October
and on four runs, and lesson 3.4 says what is not yet seen live. Whether
any of this is adequate for a given system depends on that system's
classification, its intended purpose, where it is deployed and the full
set of obligations that follow, none of which this report addresses. Of
the OWASP agentic risks [11], the policy table reaches tool misuse, the
sandbox reaches unexpected code execution, and the budgets reach rogue
agents, in each case for the calls the gate sees. Goal hijack lives in
text the gate cannot read, identity per instance and the supply chain of
tools are not addressed, and lesson 3.2 shows the taint control against
hijack being switched off in practice.

The evidence is thin and I say so. One operator wrote the runtime, the
policies and this report, and nobody has reproduced any of it. Four runs
stand behind four lessons. The runs use Claude Sonnet 5 and 5.5 through
one harness, and the cost stop, the sandbox and the session restore are
the harness's, as are the cost figures. The turn count in the log counts
assistant messages, not harness turns, so run A reports 139 against a
limit of 50. One wrong line stands in run A's log. Its resumed run
recorded "8.7193 exceeded 2.0 without a harness stop", because the
harness reports session totals and the subtraction came later, and the
chain does not allow editing it. The repository also holds a three-arm
benchmark that puts the same rules in the prompt, in the gate, or in
both, for one toy agent and nine cases of my own. It is built and not
run. A code check beating a prompt on cases I wrote would show nothing a
reader does not already believe, so it waits for cases somebody else
wrote, which is the next step.

## 5. Related work

AgentDojo [1], InjecAgent [2] and Agent Security Bench [3] measure how
often a model is hijacked on hundreds to tens of thousands of cases. This
report measures nothing of the kind and plans to borrow their cases. NeMo
Guardrails [4] checks text on the way in and out, which is where a gate
cannot see. CaMeL [5] and the design patterns of Beurer-Kellner and others
[6] move the rule out of the model's reach, as the gate does, and lesson
3.2 is what happens when such a rule is too crude. The SDK's own hooks and
sandbox [7] are the layer lesson 3.3 sits on. METR's report on the OpenAI
and Hugging Face incident [9] describes about 1,200 agents coordinating
through an artifact cache no prompt had mentioned, which is why a runtime
must record every channel. The EU AI Act's Articles 12 and 14 [10] ask for
automatic logging and human oversight, which is what the chain and the
approval path are for, without any claim that they satisfy a regulator.

## 6. Reproducing the runs

The repository is public under AGPL at github.com/QuietFlare/mainsheet.
At commit `0075744`, `pip install mainsheet`, then `mainsheet
agents/human_probe.yaml` runs a probe like run C and `mainsheet-verify
<instance id>` checks its record. The event logs, receipts and definitions
of runs A to D are in `docs/paper/data/` with the issuer's public key and
a script that verifies every receipt against the key alone, without the
author's chain. For each decision event the script checks that the
receipt the event names exists, that its signature and evidence digest
verify under the key, and that it binds to the event by record id, tool,
verdict and a decision time within five seconds of the event. On 26
October all 120 receipts across the five run folders passed, and a
scratch copy with two receipts swapped, one signature altered and one
receipt removed failed on exactly those four. The script does not check
the chain, the arguments, or what a tool did, and it needs the Vaara
package. The folder is redacted in four ways, each stated in its README. The
operator's home directory is replaced by a placeholder, the content of
run A's writes is replaced by its length and a hash, run A's longer model
text is truncated, and the refused private file is named only as such.
Queries, URLs and the questions put to the person are kept. One signed
receipt keeps an original path in its refusal reason, because editing it
would break the signature.

## 7. Conclusion

A policy in a file, a gate at the tool call and a signed record answer
the reviewer's question and the auditor's for the calls the gate sees, and four runs
of my own showed where that answer was thinner than its design. A cost
control has to live where the cost is observed. A control too blunt to
live with gets switched off by the person it protects. The harness under
a runtime is a second control plane, and a record that shows only one of
them is half a record. Oversight is a decision with a timestamp, not a
refusal. None of this is proven beyond one operator and four runs. The
next step is to put the data folder in a reader's hands and have someone
else run the verifier, and then to measure the gate on cases somebody
else wrote.

## Acknowledgments

The runtime, the policies, the runs, the decision records and the data
are the author's. The text of this report, in every section, was drafted
by Claude [12], Anthropic's model, working in Claude Code from the
author's code, logs and decision records under her direction, and was
revised by the author over several rounds. Two reviews the author
obtained from ChatGPT (OpenAI) and Grok (xAI) led to corrections, which
the author checked against the logs before accepting. The verification
script in the data folder was written the same way and tested against
altered receipts.

## References

[1] E. Debenedetti, J. Zhang, M. Balunović, L. Beurer-Kellner, M. Fischer
and F. Tramèr, "AgentDojo: A dynamic environment to evaluate prompt
injection attacks and defenses for LLM agents," NeurIPS 2024 Datasets and
Benchmarks, arXiv 2406.13352.

[2] Q. Zhan, Z. Liang, Z. Ying and D. Kang, "InjecAgent: Benchmarking
indirect prompt injections in tool-integrated large language model
agents," Findings of ACL 2024, arXiv 2403.02691.

[3] H. Zhang et al., "Agent Security Bench (ASB): Formalizing and
benchmarking attacks and defenses in LLM-based agents," ICLR 2025,
arXiv 2410.02644.

[4] T. Rebedea, R. Dinu, M. Sreedhar, C. Parisien and J. Cohen, "NeMo
Guardrails: A toolkit for controllable and safe LLM applications with
programmable rails," EMNLP 2023 System Demonstrations, arXiv 2310.10501.

[5] E. Debenedetti et al., "Defeating prompt injections by design,"
arXiv 2503.18813, 2025.

[6] L. Beurer-Kellner et al., "Design patterns for securing LLM agents
against prompt injections," arXiv 2506.08837, 2025.

[7] Anthropic, "Claude Agent SDK, Hooks" and "Claude Code, Sandboxing,"
platform.claude.com and code.claude.com, accessed October 2026.

[8] H. Sirkkavaara, Vaara, version 2.5.0, vaara.io.

[9] METR and Redwood Research, "Brief independent investigation of
agents' behavior, reasoning and collaboration in the OpenAI / Hugging
Face hacking incident," metr.org, 26 August 2026.

[10] Regulation (EU) 2024/1689 (Artificial Intelligence Act), Articles 12
and 14.

[11] OWASP GenAI Security Project, "OWASP Top 10 for Agentic Applications
for 2026," 9 December 2025, genai.owasp.org.

[12] Anthropic, Claude Fable 5.1 (model id claude-fable-5-1) in Claude
Code, October 2026, claude.com.
