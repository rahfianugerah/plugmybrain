# One background job at a time, a digest or a reset, run as `python -m plugmybrain.cli`.
# A subprocess, so a digest's memory is returned when it ends and a crash never takes the server.
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

LOG = Path(tempfile.gettempdir()) / "pmb-job.log"

# cognee logs every task at INFO, which buries the report an agent needs
_JOB_ENV = {"PYTHONUNBUFFERED": "1", "LOG_LEVEL": "ERROR", "COGNEE_LOG_FILE": "false"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class Job:
    action: str
    target: str
    process: asyncio.subprocess.Process
    started: float = field(default_factory=time.monotonic)
    reported: bool = False

    @property
    def running(self) -> bool:
        return self.process.returncode is None

    @property
    def elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    @property
    def outcome(self) -> str:
        if self.running:
            return "running"
        code = self.process.returncode
        return "finished" if code == 0 else f"failed (exit {code})"


_current: Job | None = None


def current() -> Job | None:
    return _current


async def start(action: str, target: Path, *flags: str) -> Job:
    """Start a job. Refuses while another runs: two digests at once is how 2 GiB runs out."""
    global _current
    if _current and _current.running:
        raise RuntimeError(f"a {_current.action} of {_current.target} is still running")
    with LOG.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "plugmybrain.cli",
            action,
            str(target),
            *flags,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **_JOB_ENV},
        )
    _current = Job(action, str(target), process)
    return _current


async def wait(job: Job, seconds: float) -> bool:
    """True when the job ended within `seconds`. It keeps running either way."""
    try:
        await asyncio.wait_for(asyncio.shield(job.process.wait()), timeout=max(0.0, seconds))
    except TimeoutError:
        return False
    return True


def output(limit: int = 8000) -> str:
    """The tail of the job's log."""
    text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.is_file() else ""
    lines = [line for line in _ANSI.sub("", text).splitlines() if line.strip()]
    return "\n".join(lines)[-limit:]
