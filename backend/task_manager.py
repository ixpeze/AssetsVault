import subprocess
import threading
import time
import os
import signal
import re
import logging
from datetime import datetime
from typing import Callable
import atexit
from .constants import ALLOWED_SCRIPTS

log = logging.getLogger(__name__)


class TaskManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskManager, cls).__new__(cls)
            cls._instance.tasks = {}
            cls._instance.lock = threading.Lock()
            cls._instance._completion_hooks: dict[str, list[Callable]] = {}
            atexit.register(cls._instance._cleanup_on_exit)
        return cls._instance

    def on_complete(self, task_type: str, fn: Callable) -> None:
        """
        Register a callback to fire when a task of *task_type* completes
        successfully.  Called from the app factory — keeps business logic
        (which caches to invalidate) out of TaskManager itself.
        """
        self._completion_hooks.setdefault(task_type, []).append(fn)

    def _cleanup_on_exit(self):
        for task_id, task in list(self.tasks.items()):
            if task["status"] == "running":
                self.stop_task(task_id)

    def start_task(self, script_name, task_type, args=None, cwd=None):
        # Security: only allow explicitly allowlisted scripts to be launched
        if script_name not in ALLOWED_SCRIPTS:
            log.error("[TaskManager] Blocked attempt to run non-allowlisted script: %s", script_name)
            return None

        with self.lock:
            self._cleanup_old_tasks()

            task_id = f"{task_type}_{int(time.time())}"
            cmd = ["python", "-u", script_name] + (args or [])

            try:
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"

                creationflags = 0
                preexec_fn = None
                if os.name == "nt":
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    preexec_fn = os.setsid

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=cwd or os.getcwd(),
                    bufsize=1,
                    universal_newlines=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    creationflags=creationflags,
                    preexec_fn=preexec_fn,
                )

                self.tasks[task_id] = {
                    "id":         task_id,
                    "type":       task_type,
                    "command":    " ".join(cmd),
                    "process":    process,
                    "status":     "running",
                    "start_time": datetime.now().isoformat(),
                    "params":     args,
                    "logs":       [],
                    "progress":   0,
                }

                threading.Thread(
                    target=self._monitor_task, args=(task_id,), daemon=True
                ).start()
                return task_id
            except Exception as e:
                log.error("[TaskManager] Failed to start task: %s", e)
                return None

    def _monitor_task(self, task_id):
        if task_id not in self.tasks:
            return

        task    = self.tasks[task_id]
        process = task["process"]
        error_indicators = ["ERROR:", "Failed:", "Exception:", "Traceback"]

        try:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    continue
                clean_line = line.strip()
                task["logs"].append(clean_line)
                if len(task["logs"]) > 500:
                    task["logs"].pop(0)

                if any(err in clean_line for err in error_indicators):
                    task["has_errors"] = True
                    task["error_count"] = task.get("error_count", 0) + 1

                # Progress: "Page 5/20"
                m = re.search(r"Page (\d+)/(\d+)", clean_line)
                if m:
                    task["progress"] = int(int(m.group(1)) / int(m.group(2)) * 100)

                # Progress: "[10/500]"
                m = re.search(r"\[(\d+)/(\d+)\]", clean_line)
                if m:
                    task["progress"] = int(int(m.group(1)) / int(m.group(2)) * 100)

            process.wait()
            task["status"] = "completed" if process.returncode == 0 else "failed"

            # Fire registered completion callbacks (e.g. cache invalidation).
            # Registered via on_complete() in the app factory — TaskManager
            # itself has no knowledge of what the hooks do.
            if task["status"] == "completed":
                for hook in self._completion_hooks.get(task["type"], []):
                    try:
                        hook()
                    except Exception as e:
                        log.error("[TaskManager] Completion hook error: %s", e)

                # Also emit on the event bus for decoupled subscribers
                try:
                    from .core.event_bus import bus
                    bus.emit("pipeline_completed", task_id=task_id, task_type=task["type"])
                except Exception as e:
                    log.error("[TaskManager] Event bus emit error: %s", e)

        except Exception as e:
            task["status"] = "failed"
            task["logs"].append(f"System Error: {str(e)}")
        finally:
            task["end_time"] = datetime.now().isoformat()
            if process.stdout:
                process.stdout.close()

    def get_tasks(self):
        with self.lock:
            return {
                tid: {
                    "id":         t["id"],
                    "type":       t["type"],
                    "status":     t["status"],
                    "start_time": t["start_time"],
                    "end_time":   t.get("end_time"),
                    "logs":       t["logs"][-50:],
                    "progress":   t.get("progress", 0),
                }
                for tid, t in self.tasks.items()
            }

    def stop_task(self, task_id):
        with self.lock:
            if task_id not in self.tasks:
                return False
            task = self.tasks[task_id]
            if task["status"] != "running":
                return False
            process = task["process"]
            try:
                if os.name == "nt":
                    os.kill(process.pid, signal.CTRL_C_EVENT)
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                log.warning("Error terminating process group: %s", e)
                process.terminate()
            task["status"]   = "stopped"
            task["end_time"] = datetime.now().isoformat()
            return True

    def update_task_progress(self, task_id, progress):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["progress"] = max(0, min(100, int(progress)))
                return True
        return False

    def _cleanup_old_tasks(self):
        sorted_tasks = sorted(self.tasks.items(), key=lambda x: x[1]["start_time"])
        if len(sorted_tasks) > 20:
            for tid, _ in sorted_tasks[:-20]:
                if self.tasks[tid]["status"] != "running":
                    del self.tasks[tid]


# Global singleton
task_manager = TaskManager()
