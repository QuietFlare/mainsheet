"""Local panel: the canvas of agents, their definitions, instances, and live events."""
import asyncio
import importlib
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent import system as sysmod
from agent.config import AgentConfig
from agent.runtime import Registry
from agent.telemetry import tracer

app = FastAPI(title="Mainsheet panel")
HERE = Path(__file__).resolve().parent
registry = Registry()
tracer()


class NewAgent(BaseModel):
    name: str = Field(
        pattern=r"^[a-z][a-z0-9_-]{1,31}$",
        description="lowercase letters, digits, underscore or hyphen; starts with a letter; 2 to 32 characters",
    )
    x: float = 0
    y: float = 0


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "canvas.html")


@app.get("/api/schema")
def schema() -> dict:
    return AgentConfig.model_json_schema()


@app.get("/api/system")
def get_system() -> sysmod.SystemConfig:
    return sysmod.load_system()


@app.put("/api/system")
def put_system(system: sysmod.SystemConfig) -> sysmod.SystemConfig:
    sysmod.save_system(system)
    return system


@app.post("/api/agents")
def create_agent(body: NewAgent) -> AgentConfig:
    try:
        return sysmod.create_agent(body.name, body.x, body.y)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/api/agents/{name}")
def get_agent(name: str) -> AgentConfig:
    try:
        return sysmod.agent_config(name)
    except FileNotFoundError:
        raise HTTPException(404, f"no agent {name}")


@app.put("/api/agents/{name}")
def put_agent(name: str, cfg: AgentConfig) -> AgentConfig:
    try:
        return sysmod.update_agent(name, cfg)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/agents/{name}")
def delete_agent(name: str) -> dict:
    if any(i.cfg.name == name and i.status.value == "running" for i in registry.instances.values()):
        raise HTTPException(409, "stop its running instances first")
    sysmod.delete_agent(name)
    return {"deleted": name}


@app.get("/api/agents/{name}/tools")
def agent_tools(name: str) -> dict[str, list[dict]]:
    cfg = get_agent(name)
    found = {}
    for key, spec in cfg.tools.servers.items():
        module = importlib.import_module(spec.module)
        found[key] = [{"name": t.name, "description": t.description, "allowed": t.name in spec.allow}
                      for t in module.make_tools("preview")]
    return found


@app.get("/api/instances")
def instances() -> list[dict]:
    return registry.list()


@app.post("/api/agents/{name}/run")
async def run_agent(name: str) -> dict:
    inst = registry.create(get_agent(name))
    return registry.start(inst.id).summary()


@app.post("/api/instances/{iid}/stop")
async def stop_instance(iid: str) -> dict:
    return _found(iid, registry.stop).summary()


@app.delete("/api/instances/{iid}")
async def delete_instance(iid: str) -> dict:
    try:
        _found(iid, registry.delete)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"deleted": iid}


@app.get("/api/instances/{iid}/events")
async def instance_events(iid: str) -> StreamingResponse:
    path = _found(iid, registry.get).log.path

    async def stream():
        path.touch()
        with path.open() as f:
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.strip()}\n\n"
                else:
                    await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _found(iid: str, fn):
    try:
        return fn(iid)
    except KeyError:
        raise HTTPException(404, f"no instance {iid}")


def cli() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8765)


if __name__ == "__main__":
    cli()
