import asyncio
import json
import os
import platform
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.common import CONFIG_PATH, RUNNER_LOG_PATH, STATUS_PATH, ensure_dirs, read_json, write_json


class RunnerConfig(BaseModel):
    runner_name: str = Field(default="github-runner", min_length=1)
    url: str = Field(default="", min_length=1)
    token: str = Field(default="", min_length=1)
    runner_group: str = Field(default="default")
    labels: str = Field(default="")
    ephemeral: bool = Field(default=False)
    no_default_labels: bool = Field(default=False)


def default_labels() -> str:
    arch = platform.machine().lower()
    arch_label = "ARM64" if arch in ("aarch64", "arm64") else "X64"
    return f"self-hosted,Linux,{arch_label}"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    yield


app = FastAPI(title="GitHub Runner Web", lifespan=lifespan)
templates = Jinja2Templates(directory="/app/app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    config = read_json(CONFIG_PATH)
    status = read_json(STATUS_PATH)
    configured = bool(config.get("url") and config.get("token"))
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "configured": configured,
            "config": config,
            "status": status,
            "default_labels": default_labels(),
        },
    )


@app.get("/api/status")
async def api_status():
    return {"config": read_json(CONFIG_PATH), "status": read_json(STATUS_PATH)}


@app.post("/api/config")
async def api_config(payload: RunnerConfig):
    config = {
        "runner_name": payload.runner_name.strip(),
        "url": payload.url.strip().rstrip("/"),
        "token": payload.token.strip(),
        "runner_group": payload.runner_group.strip() or "default",
        "labels": payload.labels.strip() or default_labels(),
        "ephemeral": payload.ephemeral,
        "no_default_labels": payload.no_default_labels,
    }
    write_json(CONFIG_PATH, config)
    return {"ok": True, "config": config}


@app.delete("/api/config")
async def api_config_delete():
    write_json(CONFIG_PATH, {})
    write_json(STATUS_PATH, {})
    return {"ok": True}


@app.get("/api/logs", response_class=PlainTextResponse)
async def api_logs():
    try:
        with open(RUNNER_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


@app.get("/api/logs/stream")
async def api_logs_stream():
    async def event_stream():
        last_size = 0
        while True:
            try:
                current_size = RUNNER_LOG_PATH.stat().st_size
                if current_size < last_size:
                    last_size = 0
                if current_size > last_size:
                    with open(RUNNER_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        chunk = f.read(current_size - last_size)
                    last_size = current_size
                    for line in chunk.splitlines(keepends=True):
                        payload = json.dumps({"line": line.rstrip("\n")})
                        yield f"data: {payload}\n\n".encode("utf-8")
                await asyncio.sleep(1)
            except Exception as exc:
                payload = json.dumps({"line": f"Log stream error: {exc}"})
                yield f"data: {payload}\n\n".encode("utf-8")
                await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
