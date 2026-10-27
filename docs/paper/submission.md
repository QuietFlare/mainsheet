# Submission to IEEE Software

Rules taken from the magazine's call for papers page on 2026-10-26
(computer.org, "cfp-ieee-software"). Check them once more on the day of
submission.

| rule | state |
|---|---|
| at most 4,200 words, 250 counted per figure or table | text about 3,650 plus one table, room for one figure |
| abstract at most 150 words | done, 149 |
| at most 15 references | 11 |
| three actionable insights for practitioners, as bullets, with the submission | below |
| photo of each author | needed from the author |
| author biography | slot below, needs the author |
| American English | checked, one word changed |
| headings unnumbered (Computer Society magazine style) | numbered in the draft, strip at formatting |
| template optional, encouraged | IEEE template selector, Computer Society magazine |
| submit at ieee.atyponrex.com/journal/sw-cs | not yet |
| abstract may be sent to the editor in chief first to check fit, sigrid.eldh@ieee.org | author's choice |
| IEEE DataPort for the dataset, encouraged not required | `docs/paper/data/` could go there as a zip without macOS metadata |
| arXiv preprint before submission is allowed under IEEE policy | add IEEE's "submitted for possible publication" notice to the preprint once submitted, replace with the accepted version later |

## Three actionable insights

- A cost cap checked when the run ends reports the overspend after the
  money is gone. Put the stop where cost is observed, inside the model
  loop, and record the stop like any other refusal.
- A taint rule that is one bit for the whole run leaves the operator two
  choices, no writes or writes marked safe, and they will pick the second.
  A control the operator cannot live with gets switched off; design it
  so legitimate work stays possible.
- The harness under your runtime is a second permission layer. Keep the
  operator's own settings out of agent runs, and make the record show
  both layers' decisions, or the record is half a record.

## Author biography

*[Author to write, about 60 words. Suggested facts: twenty years in
software, ten of them leading the app platform of a car maker's
infotainment system under ASPICE; now independent, building Mainsheet,
Clew and springshield under QuietFlare; contact address.]*

## Before pressing submit

1. The author reads the whole text once more.
2. A call-path figure, model to hook to gate to harness sandbox to tool,
   with the receipt written beside the decision. One figure, 250 words
   of the budget.
3. Strip the section numbers from the headings.
4. Decide on the editor-in-chief email first, or straight to the portal.
5. If arXiv first, post, then add the IEEE notice on submission.
6. Zip `docs/paper/data/` without `__MACOSX` for the upload or DataPort.
7. Record the submission date and id here.
