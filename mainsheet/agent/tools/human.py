"""The person an agent may address: one backend per process, asked through a gated tool or by the gate itself.

A backend puts a question and returns the answer, and counts the time it waited, because that time is
the person's and not the run's. The CLI attaches the terminal it was started from. The panel attaches
nothing, and a run with nobody attached gets the old refusal from the gate and an error from the tool.
"""
import asyncio
import sys
import time
from typing import Any, Protocol

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

NOBODY = "no person is attached to this run"


class Backend(Protocol):
    waited: float  # seconds spent waiting on the person, for the run clock

    async def ask(self, question: str) -> str: ...


class Waits:
    """Counts the person's time, including a question still open, so the run clock can leave it out while they think."""

    def __init__(self) -> None:
        self._done = 0.0
        self._since: float | None = None

    @property
    def waited(self) -> float:
        open_wait = time.monotonic() - self._since if self._since is not None else 0.0
        return self._done + open_wait

    def begin(self) -> None:
        self._since = time.monotonic()

    def end(self) -> None:
        if self._since is not None:
            self._done += time.monotonic() - self._since
            self._since = None


class Terminal(Waits):
    """Print the question, read one line. Reading runs off the event loop so other instances go on."""

    def __init__(self, prompt: str = "> ", out=None) -> None:
        super().__init__()
        self.prompt = prompt
        self.out = out or sys.stdout

    async def ask(self, question: str) -> str:
        self.begin()
        try:
            print(f"\n[asks you] {question}", file=self.out, flush=True)
            return (await asyncio.to_thread(input, self.prompt)).strip()
        except EOFError:
            raise RuntimeError("the terminal closed before an answer came") from None
        finally:
            self.end()


class Scripted(Waits):
    """Answers given in advance, in order. Tests use this; an exhausted script is a closed terminal."""

    def __init__(self, answers: list[str], delay: float = 0.0) -> None:
        super().__init__()
        self.answers = list(answers)
        self.questions: list[str] = []
        self.delay = delay

    async def ask(self, question: str) -> str:
        self.questions.append(question)
        if not self.answers:
            raise RuntimeError("the script has no more answers")
        self.begin()
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self.answers.pop(0)
        finally:
            self.end()


_ATTACHED: Backend | None = None


def attach(backend: Backend | None) -> None:
    """Make this the person for every run in this process. None detaches."""
    global _ATTACHED
    _ATTACHED = backend


def attached() -> Backend | None:
    return _ATTACHED


def make_tools(agent: str) -> list[SdkMcpTool]:
    @tool(
        "ask_human",
        "Put one question to the person running this agent and wait for their answer. "
        "Ask one thing at a time. The answer is their words, unedited.",
        {"question": str},
    )
    async def ask_human(args: dict[str, Any]) -> dict[str, Any]:
        person = attached()
        if person is None:
            return {"content": [{"type": "text", "text": NOBODY}], "is_error": True}
        try:
            answer = await person.ask(args["question"])
        except RuntimeError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}
        return {"content": [{"type": "text", "text": answer}]}

    return [ask_human]


def make_server(agent: str) -> dict:
    return create_sdk_mcp_server(name="human", version="1.0.0", tools=make_tools(agent))
