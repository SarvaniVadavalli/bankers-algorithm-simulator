"""
BackendClient: Python-to-C communication layer for Banker's Algorithm Simulator.

Manages the lifecycle of the compiled C backend process and handles asynchronous
bidirectional JSON Lines communication over stdio pipes.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bankers.api")


def get_project_root() -> Path:
    """Return the backend project root directory (parent of frontend)."""
    return Path(__file__).resolve().parent.parent


def resolve_backend_executable(custom_path: Optional[str | Path] = None) -> Path:
    """
    Resolve the backend executable path robustly relative to the project root.

    Checks platform-appropriate binary names ('bankers' on POSIX, 'bankers.exe' on Windows).

    Args:
        custom_path: Optional user-supplied path to the backend executable.

    Returns:
        Path to the validated executable.

    Raises:
        FileNotFoundError: If the executable is not found.
    """
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Backend executable not found at: {custom_path}")

    project_root = get_project_root()

    if sys.platform == "win32":
        candidates = [
            project_root / "bankers.exe",
            project_root / "bankers",
            project_root / "src" / "bankers.exe",
            project_root / "src" / "bankers",
        ]
    else:
        candidates = [
            project_root / "bankers",
            project_root / "bankers.exe",
            project_root / "src" / "bankers",
            project_root / "src" / "bankers.exe",
        ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    checked = ", ".join(f"'{c}'" for c in candidates)
    raise FileNotFoundError(
        f"Backend executable 'bankers' not found in project root '{project_root}'. "
        f"Candidates checked: {checked}. Please compile the backend first using 'make'."
    )


class BackendClient:
    """
    Thread-safe client for the Banker's Algorithm C backend.

    Features:
    - Launches the compiled C executable with text-mode, line-buffered pipes.
    - Sends compact JSON Lines commands to backend stdin.
    - Continuously reads and parses backend stdout in a dedicated background thread.
    - Enqueues all received messages into a thread-safe queue.Queue for Tkinter / consumers.
    - Captures backend stderr separately to prevent stream corruption.
    - Handles unexpected process crashes, pipe errors, and clean shutdown.
    """

    def __init__(self, executable_path: Optional[str | Path] = None):
        """
        Initialize the BackendClient.

        Args:
            executable_path: Optional custom path to the compiled C backend executable.
                             If omitted, it is dynamically resolved relative to the project root.
        """
        self._custom_executable_path = executable_path
        self._executable_path: Optional[Path] = (
            resolve_backend_executable(executable_path) if executable_path else None
        )
        self._process: Optional[subprocess.Popen] = None
        self._queue: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._send_lock = threading.Lock()
        self._stderr_lock = threading.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=500)
        self._stopping = False

    @property
    def executable_path(self) -> Path:
        """The resolved path to the backend executable."""
        if self._executable_path is None:
            self._executable_path = resolve_backend_executable(self._custom_executable_path)
        return self._executable_path

    def start(self) -> None:
        """
        Start the C backend process and background reader threads.

        Raises:
            RuntimeError: If the backend is already running.
            FileNotFoundError: If the backend executable cannot be located.
            OSError: If launching the backend process fails.
        """
        if self.is_running():
            raise RuntimeError("Backend process is already running.")

        # Resolve executable path if not already resolved
        exec_path = self.executable_path

        self._stopping = False

        # Drain any residual messages from previous runs
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        with self._stderr_lock:
            self._stderr_lines.clear()

        try:
            self._process = subprocess.Popen(
                [str(exec_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line-buffered
                encoding="utf-8",
            )
        except OSError as e:
            logger.error("Failed to start backend process '%s': %s", exec_path, e)
            raise

        self._stdout_thread = threading.Thread(
            target=self._stdout_reader,
            name="BankerBackendStdoutReader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader,
            name="BankerBackendStderrReader",
            daemon=True,
        )

        self._stdout_thread.start()
        self._stderr_thread.start()
        logger.info("Backend process started (PID: %d)", self._process.pid)

    def is_running(self) -> bool:
        """Return True if the backend child process is currently running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def send_command(self, command_dict: Dict[str, Any]) -> None:
        """
        Send a command dictionary to the backend as a single compact JSON Line.

        Args:
            command_dict: A dictionary matching a backend protocol command.

        Raises:
            RuntimeError: If the backend process is not active.
            BrokenPipeError: If writing to the backend stdin pipe fails.
        """
        with self._send_lock:
            if not self.is_running():
                raise RuntimeError("Cannot send command: Backend process is not running.")
            try:
                # Use compact JSON representation without unnecessary spaces
                payload = json.dumps(command_dict, separators=(",", ":")) + "\n"
                assert self._process is not None and self._process.stdin is not None
                self._process.stdin.write(payload)
                self._process.stdin.flush()
                logger.debug("Sent command: %s", command_dict.get("command"))
            except (BrokenPipeError, OSError) as e:
                logger.error("Failed writing command to backend stdin: %s", e)
                self.stop()
                raise BrokenPipeError("Backend process pipe is broken or closed.") from e

    def get_message(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve the next JSON message from the backend response queue.

        This method is safe to call from the Tkinter main thread.

        Args:
            timeout: Maximum wait time in seconds:
                     - None: Block until a message is available.
                     - 0: Non-blocking check (returns immediately).
                     - > 0: Wait up to `timeout` seconds.

        Returns:
            The parsed JSON message dictionary, or None if timeout expires / queue is empty.
        """
        try:
            if timeout is None:
                return self._queue.get()
            if timeout <= 0:
                return self._queue.get_nowait()
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain_messages(self) -> List[Dict[str, Any]]:
        """Retrieve and return all currently pending messages in the queue without blocking."""
        messages: List[Dict[str, Any]] = []
        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def get_stderr_lines(self) -> List[str]:
        """Return a copy of captured backend stderr lines for diagnostics."""
        with self._stderr_lock:
            return list(self._stderr_lines)

    def stop(self, timeout: float = 2.0) -> None:
        """
        Gracefully stop the backend process and terminate background threads.

        Closes stdin first so the backend can exit cleanly upon reaching EOF,
        falling back to terminate() and kill() if the process does not terminate within timeout.
        """
        self._stopping = True

        if self._process is None:
            return

        proc = self._process
        logger.info("Stopping backend process (PID: %s)...", proc.pid)

        # 1. Close stdin to signal EOF to protocol_run() in C
        if proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except Exception as e:
                logger.debug("Error closing stdin: %s", e)

        # 2. Wait for process to terminate cleanly
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Backend did not exit after stdin EOF; sending SIGTERM...")
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                logger.warning("Backend did not terminate after SIGTERM; sending SIGKILL...")
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except Exception as e:
                    logger.error("Error killing backend process: %s", e)
            except Exception as e:
                logger.error("Error terminating backend process: %s", e)

        # 3. Join reader threads
        if self._stdout_thread and self._stdout_thread.is_alive():
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)

        # 4. Close pipes
        if proc.stdout and not proc.stdout.closed:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc.stderr and not proc.stderr.closed:
            try:
                proc.stderr.close()
            except Exception:
                pass

        self._process = None
        logger.info("Backend process stopped.")

    # -------------------------------------------------------------------------
    # Background Thread Readers
    # -------------------------------------------------------------------------

    def _stdout_reader(self) -> None:
        """Continuously read stdout lines from the backend and enqueue parsed JSON."""
        if not self._process or not self._process.stdout:
            return

        try:
            for raw_line in iter(self._process.stdout.readline, ""):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._queue.put(msg)
                except json.JSONDecodeError as err:
                    logger.error("Malformed JSON received from backend: %s | Raw: %r", err, line)
                    self._queue.put({
                        "status": "error",
                        "message": f"Malformed JSON from backend: {err}",
                        "raw_line": line,
                    })
        except Exception as e:
            if not self._stopping:
                logger.error("Error in stdout reader thread: %s", e)
        finally:
            if not self._stopping and self._process:
                returncode = self._process.poll()
                logger.warning(
                    "Backend stdout closed unexpectedly (returncode: %s)", returncode
                )
                self._queue.put({
                    "event": "process_terminated",
                    "status": "error",
                    "message": "Backend process terminated unexpectedly",
                    "returncode": returncode,
                })

    def _stderr_reader(self) -> None:
        """Continuously read stderr lines from the backend into a diagnostic buffer."""
        if not self._process or not self._process.stderr:
            return

        try:
            for raw_line in iter(self._process.stderr.readline, ""):
                line = raw_line.strip()
                if line:
                    with self._stderr_lock:
                        self._stderr_lines.append(line)
                    logger.debug("[Backend stderr] %s", line)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Protocol Command Helpers (Strictly matching protocol.c)
    # -------------------------------------------------------------------------

    def initialize(
        self,
        customers: int,
        resources: int,
        total: List[int],
        maximum: List[List[int]],
        allocation: List[List[int]],
    ) -> None:
        """
        Send 'initialize' command with system configuration.

        Emits two responses in order:
        1. {"status": "ok", "message": "Bank initialized"}
        2. Snapshot JSON object
        """
        self.send_command({
            "command": "initialize",
            "customers": customers,
            "resources": resources,
            "total": total,
            "maximum": maximum,
            "allocation": allocation,
        })

    def snapshot(self) -> None:
        """
        Send 'snapshot' command.

        Emits one response: Snapshot JSON object containing available, allocation,
        maximum, need, safe flag, and safe_sequence.
        """
        self.send_command({"command": "snapshot"})

    def safety_check(self) -> None:
        """
        Send 'safety_check' command.

        Emits one response: Identical in structure to snapshot response.
        """
        self.send_command({"command": "safety_check"})

    def request(self, customer: int, request: List[int]) -> None:
        """
        Send 'request' command for manual customer resource allocation.

        Emits two responses in order:
        1. {"status": "granted"|"unsafe"|"exceeds_need"|"unavailable"|"invalid", "safe_sequence": [...]}
        2. Snapshot JSON object reflecting the resulting bank state.
        """
        self.send_command({
            "command": "request",
            "customer": customer,
            "request": request,
        })

    def release(self, customer: int, release: List[int]) -> None:
        """
        Send 'release' command for manual resource release.

        Emits two responses in order:
        1. {"status": "released"|"invalid"}
        2. Snapshot JSON object reflecting the resulting bank state.
        """
        self.send_command({
            "command": "release",
            "customer": customer,
            "release": release,
        })

    def start_auto(self, requests: List[List[int]]) -> None:
        """
        Send 'start_auto' command for concurrent simulation mode.

        Spawns customer threads in C backend. Emits multiple lines:
        - {"event": "customer_started", "customer": <id>}
        - {"event": "request_result", "customer": <id>, "result": <int>, "safe_sequence": [...]}
        - {"event": "customer_released", "customer": <id>} (if granted)
        - {"event": "automatic_complete", "threads_created": <n>}
        - Snapshot JSON object reflecting final state.
        """
        self.send_command({
            "command": "start_auto",
            "requests": requests,
        })

    def reset(self) -> None:
        """
        Send 'reset' command to tear down and reset the bank state.

        Emits one response: {"status": "ok", "message": "Bank reset"}
        """
        self.send_command({"command": "reset"})

    # -------------------------------------------------------------------------
    # Context Manager Support
    # -------------------------------------------------------------------------

    def __enter__(self) -> BackendClient:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

