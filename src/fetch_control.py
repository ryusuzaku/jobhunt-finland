"""One in-process refresh at a time, shared by startup, scheduler and UI."""
import asyncio
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class FetchController:
    def __init__(self, runner):
        self.runner = runner
        self.task = None
        self.state = {"status": "idle", "ok": True, "started_at": None, "finished_at": None}

    def snapshot(self):
        return dict(self.state)

    def start(self):
        if self.task is not None and not self.task.done():
            return False
        self.state = {
            "status": "running", "ok": True,
            "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
        }
        self.task = asyncio.create_task(self._execute())
        return True

    async def _execute(self):
        try:
            result = await self.runner()
            self.state.update(result)
            self.state["status"] = "success" if result.get("ok") else "error"
        except asyncio.CancelledError:
            self.state.update(status="cancelled", ok=False)
            raise
        except Exception:
            logger.exception("Job refresh failed")
            self.state.update(status="error", ok=False, error="Refresh failed. Check server logs.")
        finally:
            self.state["finished_at"] = datetime.now(timezone.utc).isoformat()
        return self.snapshot()

    async def run(self):
        self.start()
        return await asyncio.shield(self.task)

    async def close(self):
        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
