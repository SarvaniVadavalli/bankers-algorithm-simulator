"""
test_reliability.py: Comprehensive regression tests for system reliability improvements.

Validates:
1. Safe Re-initialization:
   - Valid re-initialization replaces BankState cleanly.
   - Invalid re-initialization (allocation > total, invalid dimensions) preserves the previous BankState intact.
   - State remains fully functional after rejected re-initialization without mutex corruption or leaks.
2. Strict JSON Input Validation:
   - Vector length mismatch (too few or too many elements).
   - Matrix dimension mismatch (wrong row count or column count).
   - Negative numbers rejected.
   - Integer overflow rejected.
   - Malformed brackets and non-digit tokens rejected.
   - Rejection returns descriptive error status.
3. Customer Release Verification:
   - Handled release_failed events in Automatic Mode GUI.
4. Automatic Mode Accuracy:
   - Partial thread creation reporting (threads_created < threads_expected).
   - WAITING/RUNNING customer threads are not falsely marked COMPLETED.
   - Rejection status preserved on completion.
   - "Request Stop" button semantics and feedback.
   - "Start Simulation" button restored on completion and error.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
import tkinter as tk
from pathlib import Path
from typing import Any, Dict, List, Optional

FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from automatic_mode import AutomaticModeFrame


class TestReliabilityBackend(unittest.TestCase):
    """Backend regression tests for safe re-initialization and strict JSON input parsing."""

    def setUp(self) -> None:
        self.client = BackendClient()
        self.client.start()

    def tearDown(self) -> None:
        if self.client.is_running():
            self.client.stop()

    def wait_for_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        msg = self.client.get_message(timeout=timeout)
        self.assertIsNotNone(msg, f"Timed out waiting for backend message after {timeout}s")
        return msg  # type: ignore

    def send_raw_line(self, line: str) -> None:
        """Send a raw text line directly to backend stdin."""
        assert self.client._process is not None and self.client._process.stdin is not None
        self.client._process.stdin.write(line + "\n")
        self.client._process.stdin.flush()

    def test_01_safe_reinitialization_success(self) -> None:
        """Test successful re-initialization cleanly replaces old bank with new dimensions."""
        # 1. First initialization: 3 customers, 2 resources
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        msg1 = self.wait_for_message()
        self.assertEqual(msg1.get("status"), "ok")
        msg2 = self.wait_for_message()
        self.assertEqual(msg2.get("customers"), 3)
        self.assertEqual(msg2.get("resources"), 2)

        # 2. Re-initialization: 4 customers, 3 resources
        self.client.initialize(
            customers=4,
            resources=3,
            total=[10, 10, 10],
            maximum=[[4, 3, 2], [2, 2, 2], [3, 3, 3], [1, 1, 1]],
            allocation=[[1, 0, 1], [0, 1, 0], [1, 1, 1], [0, 0, 0]],
        )
        msg3 = self.wait_for_message()
        self.assertEqual(msg3.get("status"), "ok")
        msg4 = self.wait_for_message()
        self.assertEqual(msg4.get("customers"), 4)
        self.assertEqual(msg4.get("resources"), 3)
        self.assertEqual(msg4.get("available"), [8, 8, 8])
        self.assertTrue(msg4.get("safe"))

    def test_02_safe_reinitialization_failure_preserves_original_state(self) -> None:
        """Test that failed re-initialization preserves original bank state completely."""
        # 1. Initialize valid 3x2 bank
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        self.wait_for_message()  # status ok
        snap1 = self.wait_for_message()  # snapshot
        self.assertEqual(snap1.get("customers"), 3)
        self.assertEqual(snap1.get("available"), [5, 8])

        # 2. Attempt invalid re-initialization (allocation sum exceeds total)
        # Total: [5, 5], but allocation sum for R0 is 3+3=6 > 5
        self.client.initialize(
            customers=2,
            resources=2,
            total=[5, 5],
            maximum=[[4, 4], [4, 4]],
            allocation=[[3, 2], [3, 2]],
        )
        err_msg = self.wait_for_message()
        self.assertEqual(err_msg.get("status"), "error")
        self.assertIn("configuration invalid", err_msg.get("message", "").lower())

        # 3. Verify original bank state is fully preserved via snapshot
        self.client.snapshot()
        snap2 = self.wait_for_message()
        self.assertEqual(snap2.get("status"), "ok")
        self.assertEqual(snap2.get("customers"), 3)
        self.assertEqual(snap2.get("resources"), 2)
        self.assertEqual(snap2.get("available"), [5, 8])
        self.assertEqual(snap2.get("allocation"), [[2, 1], [1, 1], [2, 0]])

        # 4. Verify safety check still runs safely on original bank
        self.client.safety_check()
        safe_msg = self.wait_for_message()
        self.assertEqual(safe_msg.get("status"), "ok")
        self.assertTrue(safe_msg.get("safe"))
        self.assertEqual(len(safe_msg.get("safe_sequence", [])), 3)

    def test_03_strict_json_vector_length_mismatch_rejected(self) -> None:
        """Test strict validation rejects vectors with wrong element count."""
        # resources = 2, but total has 3 elements: [10, 10, 10]
        raw_cmd = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10,10,10],'
            '"maximum":[[5,5],[3,3]],'
            '"allocation":[[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd)
        msg = self.wait_for_message()
        self.assertEqual(msg.get("status"), "error")
        self.assertIn("total", msg.get("message", "").lower())

        # resources = 3, but total has 2 elements: [10, 10]
        raw_cmd2 = (
            '{"command":"initialize","customers":2,"resources":3,'
            '"total":[10,10],'
            '"maximum":[[5,5,5],[3,3,3]],'
            '"allocation":[[1,1,1],[1,1,1]]}'
        )
        self.send_raw_line(raw_cmd2)
        msg2 = self.wait_for_message()
        self.assertEqual(msg2.get("status"), "error")

    def test_04_strict_json_matrix_dimensions_mismatch_rejected(self) -> None:
        """Test strict validation rejects matrices with incorrect rows or column counts."""
        # customers = 3, but maximum has only 2 rows
        raw_cmd = (
            '{"command":"initialize","customers":3,"resources":2,'
            '"total":[10,10],'
            '"maximum":[[5,5],[3,3]],'
            '"allocation":[[1,1],[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd)
        msg = self.wait_for_message()
        self.assertEqual(msg.get("status"), "error")
        self.assertIn("maximum", msg.get("message", "").lower())

        # maximum row 0 has 3 columns while resources = 2
        raw_cmd2 = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10,10],'
            '"maximum":[[5,5,5],[3,3]],'
            '"allocation":[[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd2)
        msg2 = self.wait_for_message()
        self.assertEqual(msg2.get("status"), "error")

    def test_05_strict_json_negative_and_overflow_rejected(self) -> None:
        """Test rejection of negative numbers and integer overflow in JSON input."""
        # Negative total element
        raw_cmd = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10,-5],'
            '"maximum":[[5,5],[3,3]],'
            '"allocation":[[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd)
        msg = self.wait_for_message()
        self.assertEqual(msg.get("status"), "error")

        # Huge number exceeding INT_MAX
        raw_cmd2 = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10,99999999999999999999],'
            '"maximum":[[5,5],[3,3]],'
            '"allocation":[[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd2)
        msg2 = self.wait_for_message()
        self.assertEqual(msg2.get("status"), "error")

    def test_06_strict_json_malformed_syntax_rejected(self) -> None:
        """Test rejection of malformed brackets and non-digit characters."""
        # Unclosed bracket in total
        raw_cmd = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10, 10'
        )
        self.send_raw_line(raw_cmd)
        msg = self.wait_for_message()
        self.assertEqual(msg.get("status"), "error")

        # Non-numeric token
        raw_cmd2 = (
            '{"command":"initialize","customers":2,"resources":2,'
            '"total":[10, abc],'
            '"maximum":[[5,5],[3,3]],'
            '"allocation":[[1,1],[1,1]]}'
        )
        self.send_raw_line(raw_cmd2)
        msg2 = self.wait_for_message()
        self.assertEqual(msg2.get("status"), "error")


class TestReliabilityAutomaticMode(unittest.TestCase):
    """Frontend regression tests for Automatic Mode thread states, release failure, and stop semantics."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self) -> None:
        self.client = BackendClient()
        self.client.start()
        # Initialize standard bank
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[5, 5], [4, 4], [3, 3]],
            allocation=[[1, 1], [1, 1], [1, 1]],
        )
        # Drain init messages
        self.client.get_message(timeout=3.0)
        self.client.get_message(timeout=3.0)

        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)
        self.pump_events(5)

    def tearDown(self) -> None:
        self.frame._polling_active = False
        if hasattr(self.frame, "_poll_job") and self.frame._poll_job:
            try:
                self.frame.after_cancel(self.frame._poll_job)
            except Exception:
                pass
        self.frame.destroy()
        self.pump_events(2)
        if self.client.is_running():
            self.client.stop()

    def pump_events(self, count: int = 5) -> None:
        for _ in range(count):
            self.root.update_idletasks()
            self.root.update()
            time.sleep(0.01)

    def test_07_request_stop_button_and_graceful_handling(self) -> None:
        """Test Request Stop button text and that backend process is never terminated mid-simulation."""
        # Verify button text
        self.assertEqual(self.frame.btn_stop.cget("text"), "Request Stop")

        # When idle:
        self.frame.stop_simulation()
        self.assertIn("No simulation", self.frame.lbl_banner_title.cget("text"))

        # Mark as simulating
        self.frame._is_simulating = True
        self.frame.stop_simulation()

        # Banner should inform user about atomic cycle completion
        self.assertIn("Stop Requested", self.frame.lbl_banner_title.cget("text"))
        self.assertIn("atomic 500ms cycle", self.frame.lbl_banner_title.cget("text"))

        # Backend process must remain running!
        self.assertTrue(self.client.is_running())

    def test_08_release_failed_event_handling(self) -> None:
        """Test handling of release_failed event in Automatic Mode."""
        # Simulate dispatching a release_failed event for customer 1
        fail_msg = {
            "event": "release_failed",
            "customer": 1,
            "message": "Attempted to release more resources than currently allocated.",
        }
        self.frame._handle_backend_message(fail_msg)

        state_info = self.frame._thread_states[1]
        self.assertEqual(state_info["state"], "RELEASE FAILED")
        self.assertIn("Failed to release", state_info["detail"])

        log_text = self.frame.txt_log.get("1.0", tk.END)
        self.assertIn("ERROR", log_text)
        self.assertIn("release failed", log_text.lower())

    def test_09_partial_thread_creation_reporting(self) -> None:
        """Test partial thread creation (threads_created < threads_expected) warning display."""
        self.frame._is_simulating = True
        self.frame.btn_start.configure(state="disabled", text="Simulating...")

        # 3 customers expected, but only 2 were created
        complete_msg = {
            "event": "automatic_complete",
            "threads_expected": 3,
            "threads_created": 2,
            "complete": False,
            "success": False,
        }
        self.frame._handle_backend_message(complete_msg)

        # Simulation stopped and start button restored
        self.assertFalse(self.frame._is_simulating)
        self.assertEqual(str(self.frame.btn_start.cget("state")), "normal")
        self.assertEqual(self.frame.btn_start.cget("text"), "Start Simulation")

        # Badge shows partial failure
        self.assertIn("Partial Failure", self.frame.badge_sim.cget("text"))

        # Customer 2 (index 2) was not created
        state_c2 = self.frame._thread_states[2]
        self.assertEqual(state_c2["state"], "NOT CREATED")

        # Banner indicates partial status
        self.assertIn("PARTIAL", self.frame.lbl_banner_title.cget("text"))

    def test_10_no_false_completed_for_rejected_or_unreleased_threads(self) -> None:
        """Test that threads are NOT falsely marked COMPLETED when automatic_complete arrives."""
        self.frame._is_simulating = True

        # Simulate C0 granted and released -> COMPLETED
        self.frame._handle_backend_message({"event": "customer_started", "customer": 0})
        self.frame._handle_backend_message({"event": "request_result", "customer": 0, "result": 1, "safe_sequence": [0, 1, 2]})
        self.frame._handle_backend_message({"event": "customer_released", "customer": 0})

        # Simulate C1 denied (UNSAFE) -> REJECTED
        self.frame._handle_backend_message({"event": "customer_started", "customer": 1})
        self.frame._handle_backend_message({"event": "request_result", "customer": 1, "result": 0, "safe_sequence": []})

        # Simulate C2 running but never released
        self.frame._handle_backend_message({"event": "customer_started", "customer": 2})

        # Verify pre-complete states
        self.assertEqual(self.frame._thread_states[0]["state"], "COMPLETED")
        self.assertEqual(self.frame._thread_states[1]["state"], "REJECTED")
        self.assertEqual(self.frame._thread_states[2]["state"], "RUNNING")

        # Now automatic_complete arrives
        self.frame._handle_backend_message({
            "event": "automatic_complete",
            "threads_expected": 3,
            "threads_created": 3,
            "complete": True,
            "success": True,
        })

        # C0 should be COMPLETED
        self.assertEqual(self.frame._thread_states[0]["state"], "COMPLETED")
        # C1 must REMAIN REJECTED, NOT overwritten to COMPLETED!
        self.assertEqual(self.frame._thread_states[1]["state"], "REJECTED")
        # C2 must NOT be marked COMPLETED (marked STOPPED because it did not release)
        self.assertEqual(self.frame._thread_states[2]["state"], "STOPPED")


if __name__ == "__main__":
    unittest.main()
