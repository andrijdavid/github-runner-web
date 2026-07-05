import json
import os
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response

from app.common import (
    CONFIG_PATH,
    DATA_DIR,
    RUNNER_LOG_PATH,
    STATUS_PATH,
    ensure_dirs,
    read_json,
    write_json,
)

app = Flask(__name__)


def get_default_labels():
    import platform
    arch = platform.machine().lower()
    if arch in ("aarch64", "arm64"):
        arch_label = "ARM64"
    else:
        arch_label = "X64"
    return f"self-hosted,Linux,{arch_label},umbrel"


@app.route("/")
def index():
    config = read_json(CONFIG_PATH)
    status = read_json(STATUS_PATH)
    configured = bool(config.get("url") and config.get("token"))
    return render_template(
        "index.html",
        configured=configured,
        config=config,
        status=status,
    )


@app.route("/api/status")
def api_status():
    return jsonify({
        "config": read_json(CONFIG_PATH),
        "status": read_json(STATUS_PATH),
    })


@app.route("/api/config", methods=["POST"])
def api_config():
    data = request.get_json(force=True)
    config = {
        "runner_name": (data.get("runner_name") or "umbrel-github-runner").strip(),
        "url": (data.get("url") or "").strip().rstrip("/"),
        "token": (data.get("token") or "").strip(),
        "runner_group": (data.get("runner_group") or "default").strip(),
        "labels": (data.get("labels") or get_default_labels()).strip(),
        "ephemeral": bool(data.get("ephemeral")),
        "no_default_labels": bool(data.get("no_default_labels")),
    }
    write_json(CONFIG_PATH, config)
    return jsonify({"ok": True, "config": config})


@app.route("/api/config", methods=["DELETE"])
def api_config_delete():
    config = read_json(CONFIG_PATH)
    write_json(CONFIG_PATH, {})
    write_json(STATUS_PATH, {})
    return jsonify({"ok": True})


@app.route("/api/logs")
def api_logs():
    try:
        with open(RUNNER_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    return Response(content, mimetype="text/plain")


@app.route("/api/logs/stream")
def api_logs_stream():
    def event_stream():
        path = RUNNER_LOG_PATH
        last_size = 0
        while True:
            try:
                current_size = path.stat().st_size
                if current_size < last_size:
                    last_size = 0
                if current_size > last_size:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_size)
                        chunk = f.read(current_size - last_size)
                    last_size = current_size
                    for line in chunk.splitlines(keepends=True):
                        payload = json.dumps({"line": line.rstrip("\n")})
                        yield f"data: {payload}\n\n"
                time.sleep(1)
            except Exception as exc:
                payload = json.dumps({"line": f"Log stream error: {exc}"})
                yield f"data: {payload}\n\n"
                time.sleep(2)

    return Response(event_stream(), mimetype="text/event-stream")


if __name__ == "__main__":
    ensure_dirs()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
