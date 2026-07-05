import hashlib
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.common import (
    CONFIG_PATH,
    LOG_DIR,
    RUNNER_DIR,
    RUNNER_LOG_PATH,
    RUNNER_TEMPLATE_DIR,
    STATUS_PATH,
    ensure_dirs,
    read_json,
    write_json,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("runner-manager")


def runner_installed():
    return (RUNNER_DIR / "config.sh").exists()


def install_runner():
    """Copy the runner binary template into the writable data directory."""
    if runner_installed():
        return
    logger.info("Installing runner binary into %s", RUNNER_DIR)
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    for item in RUNNER_TEMPLATE_DIR.iterdir():
        dest = RUNNER_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    (RUNNER_DIR / "_work").mkdir(exist_ok=True)


def config_fingerprint(config):
    """Stable hash of the configuration used to detect changes."""
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def build_config_args(config):
    """Build the arguments for config.sh from user configuration."""
    args = [
        "--url", config["url"],
        "--token", config["token"],
        "--name", config.get("runner_name", "umbrel-github-runner"),
        "--runnergroup", config.get("runner_group", "default") or "default",
        "--work", "_work",
    ]
    labels = config.get("labels", "").strip()
    if labels:
        args.extend(["--labels", labels])
    if config.get("no_default_labels"):
        args.append("--no-default-labels")
    if config.get("ephemeral"):
        args.append("--ephemeral")
    return args


def run_command(cmd, cwd, env=None, timeout=None):
    """Run a command and log output. Returns (returncode, stdout, stderr)."""
    logger.info("Running: %s", " ".join(cmd))
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNNER_LOG_PATH, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n### {' '.join(cmd)}\n")
        log_f.flush()
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        stdout_lines = []
        try:
            for line in process.stdout:
                line = line.rstrip()
                stdout_lines.append(line)
                log_f.write(line + "\n")
                log_f.flush()
        except Exception as exc:
            logger.exception("Error reading command output: %s", exc)
        process.wait(timeout=timeout)
        return process.returncode, "\n".join(stdout_lines), ""


class RunnerManager:
    def __init__(self):
        self.process = None
        self.current_fingerprint = None

    def read_config(self):
        return read_json(CONFIG_PATH)

    def read_status(self):
        return read_json(STATUS_PATH)

    def write_status(self, status):
        write_json(STATUS_PATH, status)

    def update_status(self, **kwargs):
        status = self.read_status()
        status.update(kwargs)
        status["last_update"] = time.time()
        self.write_status(status)

    def remove_runner(self, token):
        """Deregister the runner from GitHub using config.sh remove."""
        if not runner_installed():
            return True
        try:
            returncode, _, _ = run_command(
                ["./config.sh", "remove", "--token", token],
                cwd=RUNNER_DIR,
                timeout=120,
            )
            return returncode == 0
        except Exception as exc:
            logger.exception("Failed to remove runner: %s", exc)
            return False

    def configure_runner(self, config):
        """Run config.sh to register the runner."""
        install_runner()
        env = os.environ.copy()
        env["RUNNER_ALLOW_RUNASROOT"] = "1" if os.geteuid() == 0 else "0"
        returncode, stdout, _ = run_command(
            ["./config.sh"] + build_config_args(config),
            cwd=RUNNER_DIR,
            env=env,
            timeout=120,
        )
        return returncode == 0, stdout

    def start_runner(self):
        """Start the runner process."""
        if self.process is not None and self.process.poll() is None:
            return
        logger.info("Starting GitHub Actions runner")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(RUNNER_LOG_PATH, "a", encoding="utf-8") as log_f:
            log_f.write("\n### Starting runner\n")
            log_f.flush()
            env = os.environ.copy()
            env["RUNNER_ALLOW_RUNASROOT"] = "1" if os.geteuid() == 0 else "0"
            self.process = subprocess.Popen(
                ["./run.sh"],
                cwd=RUNNER_DIR,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
            )

    def stop_runner(self):
        """Stop the runner process gracefully."""
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.process = None
            return
        logger.info("Stopping runner process")
        self.process.send_signal(signal.SIGINT)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            logger.warning("Runner did not stop gracefully, killing")
            self.process.kill()
            self.process.wait(timeout=10)
        self.process = None

    def runner_is_alive(self):
        return self.process is not None and self.process.poll() is None

    def ensure_state(self):
        config = self.read_config()
        fingerprint = config_fingerprint(config)

        status = self.read_status()
        current_fp = status.get("fingerprint")

        if not config.get("url") or not config.get("token"):
            if self.runner_is_alive():
                self.stop_runner()
            self.update_status(
                state="not_configured",
                message="Configure the runner from the web UI.",
                fingerprint=None,
            )
            self.current_fingerprint = None
            return

        if fingerprint != current_fp:
            # Configuration changed. Stop and reconfigure.
            self.stop_runner()
            old_token = status.get("last_token", config.get("token"))
            self.remove_runner(old_token)

            self.update_status(
                state="configuring",
                message="Registering runner with GitHub...",
                fingerprint=None,
            )
            ok, stdout = self.configure_runner(config)
            if not ok:
                self.update_status(
                    state="error",
                    message=f"Runner registration failed. Check the logs. {stdout[-500:]}",
                    fingerprint=None,
                )
                self.current_fingerprint = None
                return

            status = self.read_status()
            status["fingerprint"] = fingerprint
            status["last_token"] = config.get("token")
            self.write_status(status)
            self.current_fingerprint = fingerprint

        if not self.runner_is_alive():
            self.start_runner()

        self.update_status(
            state="running" if self.runner_is_alive() else "error",
            message="Runner is active." if self.runner_is_alive() else "Runner process exited.",
        )

    def run(self):
        ensure_dirs()
        logger.info("Runner manager started")
        while True:
            try:
                self.ensure_state()
            except Exception as exc:
                logger.exception("Unexpected error in manager loop: %s", exc)
                self.update_status(state="error", message=str(exc))
            time.sleep(5)


if __name__ == "__main__":
    manager = RunnerManager()
    manager.run()
