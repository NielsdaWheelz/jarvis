"""Actual selected native process death and automatic fresh-thread completion."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path


async def main():
    private = Path(tempfile.mkdtemp(prefix="jarvis-actual-restart-"))
    os.chmod(private, 0o700)
    ready = private / "accepted.json"
    script = str(Path(__file__).with_name("live_web_probe.py"))
    environment = {
        **os.environ,
        "JARVIS_PROOF_MODE": "kill",
        "JARVIS_PROOF_KILL_READY": str(ready),
    }
    log = (private / "killed.log").open("wb")
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        script,
        env=environment,
        stdout=log,
        stderr=asyncio.subprocess.STDOUT,
    )
    result = None
    try:
        async with asyncio.timeout(60):
            while not ready.exists():
                if worker.returncode is not None:
                    raise AssertionError(
                        "actual worker exited before accepted turn; inspect "
                        + str(private / "killed.log")
                    )
                await asyncio.sleep(0.02)
        state = json.loads(ready.read_text())
        assert state["worker_pid"] == worker.pid
        worker.kill()
        await worker.wait()
        assert worker.returncode < 0
        print(
            json.dumps(
                {
                    "phase": "actual_selected_native_worker_killed",
                    "attempt_id": state["attempt_id"],
                }
            ),
            flush=True,
        )
        resumed = {
            **os.environ,
            "JARVIS_PROOF_MODE": "restart",
            "JARVIS_PROOF_CONVERSATION": state["conversation"],
            "JARVIS_PROOF_INPUT_ID": state["input_id"],
        }
        result = await asyncio.create_subprocess_exec(
            sys.executable, script, env=resumed
        )
        async with asyncio.timeout(180):
            assert await result.wait() == 0
        print(
            (
                "actual process death -> fenced old callbacks -> automatic new "
                "native thread -> original input completed: GREEN"
            ),
            flush=True,
        )
    finally:
        if worker.returncode is None:
            worker.kill()
            await worker.wait()
        if result is not None and result.returncode is None:
            result.kill()
            await result.wait()
        log.close()


asyncio.run(main())
