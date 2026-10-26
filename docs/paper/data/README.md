# Data behind the experience report

One folder per run named in the paper. Each holds the run's event log, the
signed receipt for every gate decision in it, and the agent definition
that produced it. `issuer-es256.pub.pem` is the public key the receipts
were signed under. `verify.py` checks every receipt against that key
without the author's audit chain.

```bash
pip install vaara
python docs/paper/data/verify.py
```

`verify.py` needs the `vaara` package, the same library Mainsheet signs
with (2.5.0 at the time of writing). It checks that every decision's
receipt exists, verifies under the key, and binds to the event by record
id, tool, verdict and time. It does not check the author's chain, the
arguments, or what a tool did.

| folder | instance | date | run |
|---|---|---|---|
| A | aurae-research-26c87720 | 2026-10-20 | desk research, 16 questions, cap 2.00 USD, resumed once. The log holds both runs, 94 calls then 10, and the paper's counts are the first |
| B | aurae-research-3d062e9f | 2026-10-20 | the same agent, cap 0.10 USD, stopped by the harness |
| C | human_probe-1fcba1f5 | 2026-10-26 | probe for the human path, 60 s timeout |
| D | aurae-decision-record-fd147e2f | 2026-10-26 | interview agent, four questions, cancelled |
| D-first | aurae-decision-record-a7d7e75c | 2026-10-26 | first attempt of D, folder listing refused |

The definition for A is `research-agent.yaml` with the cap at 2.00. B's is
the same file with the cap at 0.10 and nothing else changed. C and D ship
the plugin whose skill is part of their digest.

What the logs hold. `events.jsonl` records every tool call with its
arguments, every gate decision with the argument digest and the receipt
id, every violation with its reason, the model's text between calls, and
the run's start and end with cost and token counts. Receipts hold the
decision, the tool name, the agent, the time and the signature, and not
the arguments or their digest. The digest is on the decision event.
The person's answers to `ask_human` are not logged. The questions are.

Not included. The author's audit chain (`trail/audit.db`), the harness
transcripts, and the agents' work folders. The chain holds other runs
and stays with the author. A receipt verifies on its own with the key.

Redacted. The author's home directory is replaced by `/Users/operator`
in every log and definition. In run A the content of each `Write` call
is replaced by its length and a hash, and model text longer than 300
characters is truncated, because the file written was the author's own
market research. The private file named in run A's refused read is
replaced by `[private file]`. Search queries, fetched URLs and the
questions put to the person are kept. The decision events' argument
digests are over the original arguments and no longer match the
redacted inputs. One receipt in D-first carries the original path in
its refusal reason and is left as signed, since editing it would break
the signature. Nothing else was changed.
