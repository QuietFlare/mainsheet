---
name: decision-record
description: Write an Aurae decision record in the author's own words. Use when the task is to record a design decision for docs/decisions.
---

Aurae keeps each design decision as one numbered markdown file in docs/decisions. Read the two
records the task points at first, for the shape, then the notes it names, for the context.

The record has these sections in this order:

```
# 000N Topic: Choice
Status: accepted
## Context
## Decision drivers
## Considered options
## Decision
## Consequences
```

Context is two to four sentences on what Aurae is and the situation that forced the choice.
Decision drivers are three to five short lines, each one thing the choice must serve.
Considered options is a table with the columns Option, Does well, Costs, Choose it instead when.
The chosen option comes first, then two or three others.
Decision is the author's words, first person, copied unedited from their answers.
Consequences are three to five short paragraphs on what follows for the code, the install and
the next modules.

How to work:

1. Ask the person with ask_human, one question at a time, in this order: confirm the topic and
   the choice, what forced the choice now, the drivers, which other options they weighed and why
   each lost, their reason for the choice in their own words, and what it commits them to. Six
   questions, plus at most one follow-up where an answer is too thin to fill a section.
2. Draft Context, Decision drivers, Considered options and Consequences from their answers and the
   notes. The Decision section is their words exactly, spelling untouched. Add nothing they did
   not say.
3. Plain English. No em dashes, no semicolons, no bullet lists inside the table. Do not cite
   record numbers in the prose. State the reason instead.
4. Put the whole draft in one last ask_human question and ask whether to write it. Write only
   after a yes, to 000N-topic-slug.md in the working folder, with the number the task gives.
5. Say where the file is and stop.
