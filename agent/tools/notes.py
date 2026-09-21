"""Apple Notes tools bound to one agent: read any note, write only into that agent's folder."""
import asyncio
import subprocess
from typing import Any

from claude_agent_sdk import SdkMcpTool, ToolAnnotations, create_sdk_mcp_server, tool

SOURCE_NOTE = "Standup"


def _osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


async def _run(script: str) -> str:
    """Run AppleScript off the event loop so one slow call cannot stall other instances."""
    return await asyncio.to_thread(_osascript, script)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


FIXTURE_FIELDS = ["source_note"]


def fixture(agent: str, fields: dict[str, str]) -> None:
    """Plant the source note for a test run, replacing any existing one."""
    cleanup(agent)
    body = fields.get("source_note", "")
    if body == "":
        return
    _osascript(f'tell application "Notes" to make new note with properties '
               f'{{name:{_quote(SOURCE_NOTE)}, body:{_quote(body)}}}')


def cleanup(agent: str) -> None:
    """Remove the source note and everything the agent wrote in its folder."""
    for script in (
        f'tell application "Notes" to delete (every note whose name is {_quote(SOURCE_NOTE)})',
        f'tell application "Notes" to if exists folder {_quote("Mainsheet")} then '
        f'tell folder {_quote("Mainsheet")} to if exists folder {_quote(agent)} then '
        f'delete (every note of folder {_quote(agent)})',
    ):
        try:
            _osascript(script)
        except RuntimeError:
            pass


def artifact(agent: str) -> str:
    """Everything the agent wrote in its folder, for output assertions."""
    try:
        return _osascript(f'tell application "Notes" to get plaintext of every note of folder {_quote(agent)} '
                          f'of folder {_quote("Mainsheet")}')
    except RuntimeError:
        return ""


def preflight(agent: str) -> None:
    """Refuse to start when the source note is missing."""
    if _osascript(f'tell application "Notes" to exists note {_quote(SOURCE_NOTE)}') != "true":
        raise SystemExit(f"missing input: note {SOURCE_NOTE!r}")


def make_tools(agent: str) -> list[SdkMcpTool]:
    folder = f"Mainsheet/{agent}"

    @tool(
        "notes_read",
        "Return the plain text of the note with this exact title.",
        {"title": str},
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def notes_read(args: dict[str, Any]) -> dict[str, Any]:
        try:
            text = await _run(f'tell application "Notes" to get plaintext of note {_quote(args["title"])}')
        except RuntimeError as exc:
            return {"content": [{"type": "text", "text": f"no note titled {args['title']!r}: {exc}"}],
                    "is_error": True}
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "notes_write",
        f"Create a note with this title and body in the folder {folder}. Cannot write anywhere else.",
        {"title": str, "body": str},
    )
    async def notes_write(args: dict[str, Any]) -> dict[str, Any]:
        parent, _, child = folder.partition("/")
        script = f"""
        tell application "Notes"
            if not (exists folder {_quote(parent)}) then make new folder with properties {{name:{_quote(parent)}}}
            tell folder {_quote(parent)}
                if not (exists folder {_quote(child)}) then make new folder with properties {{name:{_quote(child)}}}
                tell folder {_quote(child)}
                    make new note with properties {{name:{_quote(args["title"])}, body:{_quote(args["body"])}}}
                end tell
            end tell
        end tell
        """
        try:
            await _run(script)
        except RuntimeError as exc:
            return {"content": [{"type": "text", "text": f"could not write note: {exc}"}], "is_error": True}
        return {"content": [{"type": "text", "text": f"wrote {args['title']!r} to {folder}"}]}

    return [notes_read, notes_write]


def make_server(agent: str) -> dict:
    return create_sdk_mcp_server(name="notes", version="1.0.0", tools=make_tools(agent))
