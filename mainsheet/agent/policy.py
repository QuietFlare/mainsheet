"""Policy: what an agent may do, decided in code before each tool call, with every denial a violation."""
import hashlib
import json
import re
from typing import Literal

from claude_agent_sdk import HookMatcher
from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]


class ArgRule(BaseModel):
    pattern: str


class ToolRule(BaseModel):
    allow: bool = True
    approval: Literal["none", "human"] = "none"
    irreversible: bool = False
    untrusted_output: bool = False
    args: dict[str, ArgRule] = {}


class DenyPattern(BaseModel):
    pattern: str
    reason: str
    severity: Severity = "high"


class Budgets(BaseModel):
    max_tool_calls: int = Field(default=50, ge=1)
    max_cost_usd: float = Field(default=1.0, gt=0)


class Network(BaseModel):
    """Hosts that commands run by the agent may reach. Empty means none.

    Enforced at the process boundary by the harness sandbox (Seatbelt on macOS,
    bubblewrap on Linux), not by the gate: a rule can be argued with, a closed
    socket cannot. The model call itself is made by the harness outside the
    sandbox and is unaffected.
    """
    allow: list[str] = []


class Policy(BaseModel):
    version: int = 1
    tools: dict[str, ToolRule] = {}
    deny_patterns: list[DenyPattern] = []
    budgets: Budgets = Budgets()
    network: Network = Network()


class Decision(BaseModel):
    allow: bool
    rule: str
    reason: str = ""
    severity: Severity | None = None


def short_name(tool_name: str) -> str:
    """mcp__server__tool -> tool; built-ins unchanged."""
    return tool_name.split("__")[-1] if tool_name.startswith("mcp__") else tool_name


def args_digest(tool_input: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(tool_input, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Gate:
    """Per-instance state for the policy: counts, taint, and denials that stay in force."""

    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.tool_calls = 0
        self.tainted = False
        self.denied: set[tuple[str, str]] = set()

    def pre(self, tool_name: str, tool_input: dict) -> Decision:
        name = short_name(tool_name)
        digest = args_digest(tool_input)
        if (name, digest) in self.denied:
            return Decision(allow=False, rule="denial_continuity", severity="high",
                            reason="this call was already denied; a retry cannot change that")
        rule = self.policy.tools.get(name)
        if rule is None:
            return self._deny(name, digest, "unknown_tool", "critical", f"{name} is not in the policy")
        if not rule.allow:
            return self._deny(name, digest, "tool_not_allowed", "high", f"{name} is not allowed")
        for arg, spec in rule.args.items():
            value = str(tool_input.get(arg, ""))
            if not re.search(spec.pattern, value):
                return self._deny(name, digest, f"arg:{arg}", "medium",
                                  f"{name}.{arg} must match {spec.pattern!r}")
        for dp in self.policy.deny_patterns:
            for value in _strings(tool_input):
                if re.search(dp.pattern, value):
                    return self._deny(name, digest, f"pattern:{dp.pattern}", dp.severity, dp.reason)
        if rule.irreversible and self.tainted:
            return self._deny(name, digest, "tainted_irreversible", "critical",
                              f"{name} is irreversible and this session consumed untrusted output")
        if rule.approval == "human":
            return self._deny(name, digest, "approval_required", "medium",
                              f"{name} requires human approval, which is not available in this run")
        if self.tool_calls >= self.policy.budgets.max_tool_calls:
            return self._deny(name, digest, "budget:tool_calls", "medium",
                              f"tool call budget of {self.policy.budgets.max_tool_calls} reached")
        self.tool_calls += 1
        return Decision(allow=True, rule="allowed")

    def post(self, tool_name: str, tool_response=None) -> Decision | None:
        """After a call: mark taint, and surface a sandbox violation as a critical decision."""
        rule = self.policy.tools.get(short_name(tool_name))
        if rule and rule.untrusted_output:
            self.tainted = True
        violation = sandbox_violation(tool_response)
        if violation:
            return Decision(allow=False, rule="sandbox:network", severity="critical", reason=violation)
        return None

    def _deny(self, name: str, digest: str, rule: str, severity: Severity, reason: str) -> Decision:
        self.denied.add((name, digest))
        return Decision(allow=False, rule=rule, severity=severity, reason=reason)


VIOLATION = re.compile(r"deny network-outbound [^\s`'\"]+")


def sandbox_violation(tool_response) -> str | None:
    """The harness sandbox reports a blocked connection inside the tool result; pull out the one line that matters."""
    if tool_response is None:
        return None
    text = tool_response if isinstance(tool_response, str) else json.dumps(tool_response, default=str)
    m = VIOLATION.search(text)
    return m.group(0) if m else None


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def make_hooks(gate: Gate, on_decision) -> dict[str, list[HookMatcher]]:
    """SDK hooks that consult the gate before every call and update it after. on_decision(tool, input, decision) records."""

    async def pre(input_data, tool_use_id, context):
        decision = gate.pre(input_data["tool_name"], input_data.get("tool_input") or {})
        on_decision(input_data["tool_name"], input_data.get("tool_input") or {}, decision)
        if decision.allow:
            return {}
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason,
        }}

    async def post(input_data, tool_use_id, context):
        # A failed command arrives as PostToolUseFailure with `error`; a successful one as PostToolUse with `tool_response`.
        response = input_data.get("tool_response", input_data.get("error"))
        decision = gate.post(input_data["tool_name"], response)
        if decision is not None:
            on_decision(input_data["tool_name"], input_data.get("tool_input") or {}, decision)
        return {}

    return {
        "PreToolUse": [HookMatcher(hooks=[pre])],
        "PostToolUse": [HookMatcher(hooks=[post])],
        "PostToolUseFailure": [HookMatcher(hooks=[post])],
    }
