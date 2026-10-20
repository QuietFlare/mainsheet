# Sharing benchmark

Does a group of agents spend less when they share a prompt prefix and a memory? Three agents, six research questions, two questions each, one run per arm, same cost cap per agent.

- Arm A, `arm_a.yaml`: nothing shared. The agent's own part comes first in the task, no memory.
- Arm B, `arm_b.yaml`: the shared question list first and the agent's part last, so the prefix is identical across agents, plus the shared memory server (`mainsheet.agent.tools.memory`). Each reader is told to ask the memory before the web and to store a digest after reading.

Run one arm:

```bash
.venv/bin/python bench/run.py bench/arm_b.yaml --agents 3
```

The runner starts the agents at once, waits, and writes a table to `bench/results/` from the instances' event logs. Every number is read back from a log line.

## Results, one run each, Sonnet 5.5, cap 0.35 USD per agent

Arm A, nothing shared:

| instance | seconds | calls | fetches | recalls | remembers | input | cache_write | cache_read | output | usd | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bench-a-1 | 50.5 | 7 | 6 | 0 | 0 | 8 | 14500 | 32321 | 1446 | 0.3530 | 1 |
| bench-a-2 | 38.0 | 6 | 5 | 0 | 0 | 4 | 12797 | 8066 | 916 | 0.3831 | 1 |
| bench-a-3 | 50.2 | 7 | 5 | 0 | 0 | 6 | 12900 | 19535 | 1440 | 0.3718 | 2 |
| total | 50.5 | 20 | 16 | 0 | 0 | 18 | 40197 | 59922 | 3802 | 1.1078 | 4 |

Arm B, shared prefix and memory:

| instance | seconds | calls | fetches | recalls | remembers | input | cache_write | cache_read | output | usd | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bench-b-1 | 52.5 | 9 | 4 | 3 | 1 | 10 | 16181 | 43953 | 3881 | 0.3484 | 0 |
| bench-b-2 | 48.3 | 10 | 4 | 3 | 2 | 8 | 13458 | 29752 | 2945 | 0.3576 | 1 |
| bench-b-3 | 56.1 | 12 | 5 | 3 | 3 | 8 | 13752 | 29647 | 3741 | 0.3830 | 1 |
| total | 56.1 | 31 | 13 | 9 | 6 | 26 | 43391 | 103352 | 10567 | 1.0890 | 2 |

Every agent in both arms answered its two questions and stopped on the cost cap. The violations are the cap stops, plus two denied PDF reads in arm A.

## Reading

Sharing saved nothing in this run. The reasons are in the logs.

Nobody read the memory. All nine recalls came first, within the first seconds, when the memory was empty, because the three agents started within six milliseconds of each other and each was told to ask before fetching. The six entries were written at the end of each run, after every other agent had already fetched. Memory only pays when a reader arrives after a writer. Simultaneous start guarantees the opposite.

Nobody read another agent's prefix. Cache writes per agent are the same in both arms, about 13,000 to 16,000 tokens each. A shared prefix is written once and read by the others only if they start after the write lands, and only if the prefix is byte-identical. Three simultaneous first requests all miss. The harness also places the working directory in the system prompt, and each instance has its own, so the prefixes were never identical in the first place.

Sharing cost output. Arm B produced 2.8 times the output tokens, because the digests written to memory are output, and output is the expensive half.

The cache-read column is not evidence of sharing. The harness caches within a session, so every agent reads its own prefix back on every turn. Arm B's higher figure comes from its extra turns, not from the other agents.

The question list did not overlap enough. Two questions per agent on distinct topics means the agents mostly needed different pages. The memory would help a swarm whose members read the same sources, which this one was built to simulate and did not.

## What would change the result

Stagger the starts by the time of one fetch, so the second agent's recall can hit. Give the agents overlapping sources, or one reader that fills the memory before the others start. Run the instances in one working directory, or strip it from the prompt, so the prefix can be shared at all. Recall once at the start, not before every fetch, when the memory is known to be empty. Then run each arm more than once.
