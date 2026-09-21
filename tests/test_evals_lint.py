from evals.cases import Case, Suite
from evals.generate import lint, normalise_name


def test_normalise_name():
    assert normalise_name("Forbidden Tool: write outside title-pattern!") == "forbidden_tool_write_outside_title_pattern"
    assert normalise_name("9lives") == "case_9lives"
    assert len(normalise_name("x" * 100)) == 63


def case(**kw) -> Case:
    base = dict(name="case_x", category="happy_path", fixture={"source_note": "x"})
    return Case.model_validate({**base, **kw})


def test_missing_input_is_made_definite():
    s = Suite(agent="a", cases=[case(category="missing_input", behaviour={"tools_called": ["notes_read"]}, judge="anything", runs=3)])
    lint(s)
    c = s.cases[0]
    assert c.behaviour.tools_called == [] and c.behaviour.error_includes == "missing input"
    assert c.judge is None and c.runs == 1 and c.pass_rate == 1.0


def test_budget_incidents_not_forbidden():
    s = Suite(agent="a", cases=[case(category="budget", behaviour={"incidents_max": 0})])
    warnings = lint(s)
    assert s.cases[0].behaviour.incidents_max is None and warnings


def test_low_turns_raised_and_judge_about_tools_flagged():
    s = Suite(agent="a", cases=[case(behaviour={"max_turns": 3}, judge="Exactly one notes_read call occurred")])
    warnings = lint(s)
    assert s.cases[0].behaviour.max_turns == 5
    assert any("judge mentions tool usage" in w for w in warnings)


def test_denial_case_does_not_fix_executed_tools():
    s = Suite(agent="a", cases=[case(category="forbidden_tool", behaviour={"tools_called": ["notes_read"], "incidents_min": 1})])
    lint(s)
    assert s.cases[0].behaviour.tools_called is None
