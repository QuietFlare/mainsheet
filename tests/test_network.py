"""Egress: the policy's network allow list becomes the harness sandbox, and a blocked connection is a violation."""
from mainsheet.agent.config import sandbox_settings
from mainsheet.agent.policy import Gate, Network, Policy, ToolRule, sandbox_violation


def test_default_is_no_egress():
    assert Policy().network.allow == []
    s = sandbox_settings(Policy())
    assert s["enabled"] is True
    assert s["allowUnsandboxedCommands"] is False
    assert s["excludedCommands"] == []
    assert s["network"]["allowedDomains"] == []


def test_allow_list_is_passed_through():
    s = sandbox_settings(Policy(network=Network(allow=["example.com"])))
    assert s["network"]["allowedDomains"] == ["example.com"]


def test_violation_is_extracted_from_tool_response():
    resp = {"stdout": "000", "stderr": "curl: (56) CONNECT tunnel failed, response 403\n"
            "Sandbox violation reported: `deny network-outbound example.com:443 (user denied)`"}
    assert sandbox_violation(resp) == "deny network-outbound example.com:443"
    assert sandbox_violation("all fine") is None
    assert sandbox_violation(None) is None


def test_post_reports_violation_as_critical_decision():
    gate = Gate(Policy(tools={"Bash": ToolRule()}))
    d = gate.post("Bash", "Sandbox violation reported: `deny network-outbound evil.example:443 (user denied)`")
    assert d is not None and d.allow is False
    assert d.rule == "sandbox:network" and d.severity == "critical"
    assert gate.post("Bash", "ok") is None
