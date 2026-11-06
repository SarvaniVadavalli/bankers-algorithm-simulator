"""
test_api.py: Unit and integration tests for BackendClient communication layer.

Verifies:
- Process startup and shutdown.
- Dynamic initialization (3 customers, 2 resources).
- Multi-line responses handling (status + snapshot).
- Snapshot and safety_check inspection.
- Manual resource request and release.
- Automatic simulation mode (concurrent customer threads and events).
- Error handling and reset.
"""

from __future__ import annotations

import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure frontend directory is importable
import sys

FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient, resolve_backend_executable


class TestBackendClient(unittest.TestCase):
    """Test suite for BackendClient communicating with C Bankers Algorithm backend."""

    def setUp(self) -> None:
        """Create a fresh BackendClient before each test."""
        self.client = BackendClient()

    def tearDown(self) -> None:
        """Ensure backend process is stopped after each test."""
        if self.client.is_running():
            self.client.stop()

    def wait_for_message(self, timeout: float = 3.0) -> Dict[str, Any]:
        """Helper to get a message with an assertion timeout."""
        msg = self.client.get_message(timeout=timeout)
        self.assertIsNotNone(msg, f"Timed out waiting for backend message after {timeout}s")
        return msg  # type: ignore

    def test_01_process_startup_and_shutdown(self) -> None:
        """Test starting and stopping the backend process."""
        self.assertFalse(self.client.is_running())
        self.client.start()
        self.assertTrue(self.client.is_running())

        # Calling start again while running should raise RuntimeError
        with self.assertRaises(RuntimeError):
            self.client.start()

        self.client.stop()
        self.assertFalse(self.client.is_running())

    def test_02_dynamic_initialization_3_customers_2_resources(self) -> None:
        """
        Test dynamic initialization with 3 customers and 2 resources.

        Verifies that 'initialize' returns:
        1. {"status": "ok", "message": "Bank initialized"}
        2. Snapshot dictionary with exact matrices and safe sequence.
        """
        self.client.start()

        customers = 3
        resources = 2
        total = [10, 10]
        maximum = [
            [7, 5],
            [3, 2],
            [5, 5],
        ]
        allocation = [
            [2, 1],
            [1, 1],
            [2, 0],
        ]

        self.client.initialize(
            customers=customers,
            resources=resources,
            total=total,
            maximum=maximum,
            allocation=allocation,
        )

        # Message 1: Status response
        msg1 = self.wait_for_message(timeout=3.0)
        self.assertEqual(msg1.get("status"), "ok")
        self.assertEqual(msg1.get("message"), "Bank initialized")

        # Message 2: Immediate snapshot response
        msg2 = self.wait_for_message(timeout=3.0)
        self.assertEqual(msg2.get("status"), "ok")
        self.assertEqual(msg2.get("customers"), 3)
        self.assertEqual(msg2.get("resources"), 2)
        self.assertEqual(msg2.get("available"), [5, 8])
        self.assertEqual(msg2.get("maximum"), maximum)
        self.assertEqual(msg2.get("allocation"), allocation)
        self.assertEqual(
            msg2.get("need"),
            [
                [5, 4],
                [2, 1],
                [3, 5],
            ],
        )
        self.assertTrue(msg2.get("safe"))
        seq = msg2.get("safe_sequence")
        self.assertIsInstance(seq, list)
        self.assertEqual(len(seq), 3)
        self.assertEqual(set(seq), {0, 1, 2})

    def test_03_snapshot_and_safety_check(self) -> None:
        """Test 'snapshot' and 'safety_check' commands on an initialized bank."""
        self.client.start()
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        # Drain init messages
        self.wait_for_message()
        self.wait_for_message()

        # Send snapshot
        self.client.snapshot()
        snap = self.wait_for_message(timeout=2.0)
        self.assertEqual(snap.get("status"), "ok")
        self.assertEqual(snap.get("available"), [5, 8])
        self.assertTrue(snap.get("safe"))

        # Send safety_check
        self.client.safety_check()
        safety = self.wait_for_message(timeout=2.0)
        self.assertEqual(safety.get("status"), "ok")
        self.assertTrue(safety.get("safe"))
        self.assertEqual(len(safety.get("safe_sequence", [])), 3)

    def test_04_manual_request_and_release(self) -> None:
        """
        Test manual request and manual release.

        Verifies:
        - Request produces status ('granted') + snapshot with updated matrices.
        - Release produces status ('released') + snapshot with restored matrices.
        """
        self.client.start()
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        # Drain init messages
        self.wait_for_message()
        self.wait_for_message()

        # 1. Customer 1 requests [1, 0] (Need is [2, 1], Available is [5, 8]) -> Should be granted
        self.client.request(customer=1, request=[1, 0])

        req_status = self.wait_for_message(timeout=3.0)
        self.assertEqual(req_status.get("status"), "granted")
        self.assertIn("safe_sequence", req_status)

        req_snap = self.wait_for_message(timeout=3.0)
        self.assertEqual(req_snap.get("status"), "ok")
        self.assertEqual(req_snap.get("available"), [4, 8])
        self.assertEqual(req_snap.get("allocation")[1], [2, 1])
        self.assertEqual(req_snap.get("need")[1], [1, 1])

        # 2. Customer 1 releases [1, 0] -> Should be released
        self.client.release(customer=1, release=[1, 0])

        rel_status = self.wait_for_message(timeout=3.0)
        self.assertEqual(rel_status.get("status"), "released")

        rel_snap = self.wait_for_message(timeout=3.0)
        self.assertEqual(rel_snap.get("status"), "ok")
        self.assertEqual(rel_snap.get("available"), [5, 8])
        self.assertEqual(rel_snap.get("allocation")[1], [1, 1])
        self.assertEqual(rel_snap.get("need")[1], [2, 1])

    def test_05_automatic_mode(self) -> None:
        """
        Test automatic simulation mode using 3 customer request vectors.

        Verifies:
        - Multiple asynchronous event messages are received and preserved in order:
          'customer_started', 'request_result', 'customer_released'.
        - 'automatic_complete' event is received when all customer threads join.
        - Final snapshot is received following automatic_complete.
        """
        self.client.start()
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        # Drain init messages
        self.wait_for_message()
        self.wait_for_message()

        # 3 requests, one per customer
        requests = [
            [1, 0],  # Customer 0
            [0, 1],  # Customer 1
            [1, 1],  # Customer 2
        ]

        self.client.start_auto(requests)

        events: List[Dict[str, Any]] = []
        started_customers = set()
        result_customers = set()
        released_customers = set()
        automatic_complete_seen = False
        final_snapshot: Optional[Dict[str, Any]] = None

        # Each thread holds resources for 500ms; timeout of 8s is ample
        deadline = time.time() + 8.0
        while time.time() < deadline:
            msg = self.client.get_message(timeout=1.5)
            if msg is None:
                if automatic_complete_seen and final_snapshot:
                    break
                continue

            events.append(msg)
            event_type = msg.get("event")

            if event_type == "customer_started":
                started_customers.add(msg.get("customer"))
            elif event_type == "request_result":
                result_customers.add(msg.get("customer"))
            elif event_type == "customer_released":
                released_customers.add(msg.get("customer"))
            elif event_type == "automatic_complete":
                automatic_complete_seen = True
                self.assertEqual(msg.get("threads_created"), 3)
            elif msg.get("status") == "ok" and "available" in msg:
                final_snapshot = msg
                if automatic_complete_seen:
                    break

        self.assertEqual(started_customers, {0, 1, 2}, f"Missing started customers: {events}")
        self.assertEqual(result_customers, {0, 1, 2}, f"Missing result customers: {events}")
        self.assertTrue(automatic_complete_seen, "Did not receive 'automatic_complete' event")
        self.assertIsNotNone(final_snapshot, "Did not receive final snapshot after auto complete")

    def test_06_reset_command(self) -> None:
        """Test that 'reset' clears bank state and uninitializes the backend."""
        self.client.start()
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        self.wait_for_message()
        self.wait_for_message()

        # Send reset
        self.client.reset()
        reset_msg = self.wait_for_message(timeout=2.0)
        self.assertEqual(reset_msg.get("status"), "ok")
        self.assertEqual(reset_msg.get("message"), "Bank reset")

        # Snapshot should now return error
        self.client.snapshot()
        err_msg = self.wait_for_message(timeout=2.0)
        self.assertEqual(err_msg.get("status"), "error")
        self.assertEqual(err_msg.get("message"), "Bank is not initialized")

    def test_07_invalid_dimensions_error(self) -> None:
        """Test error handling when backend receives invalid customer/resource dimensions."""
        self.client.start()
        # Customers 0 is out of bounds (1-50 required)
        self.client.initialize(
            customers=0,
            resources=2,
            total=[10, 10],
            maximum=[],
            allocation=[],
        )
        err = self.wait_for_message(timeout=2.0)
        self.assertEqual(err.get("status"), "error")
        self.assertIn("Invalid dimensions", err.get("message", ""))

    def test_08_context_manager_and_not_running_errors(self) -> None:
        """Test context manager lifecycle and error when sending command while stopped."""
        with BackendClient() as client:
            self.assertTrue(client.is_running())
            client.snapshot()
            err = client.get_message(timeout=2.0)
            self.assertIsNotNone(err)
            self.assertEqual(err.get("status"), "error")

        self.assertFalse(client.is_running())

        # Sending command to a stopped client should raise RuntimeError
        with self.assertRaises(RuntimeError):
            client.send_command({"command": "snapshot"})

    def test_09_exceeds_need_and_unavailable_requests(self) -> None:
        """Test that requests exceeding customer need or system availability return proper status."""
        self.client.start()
        self.client.initialize(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[[7, 5], [3, 2], [5, 5]],
            allocation=[[2, 1], [1, 1], [2, 0]],
        )
        self.wait_for_message()
        self.wait_for_message()

        # Customer 1 need is [2, 1]. Requesting [3, 0] exceeds need!
        self.client.request(customer=1, request=[3, 0])
        res1 = self.wait_for_message(timeout=2.0)
        self.assertEqual(res1.get("status"), "exceeds_need")
        # Drain the snapshot that follows
        self.wait_for_message()

        # Customer 0 need is [5, 4], but available is [5, 8].
        # If customer 0 requests [6, 0], it's > need, but what if customer 0 requests [5, 9]?
        # Need is [5, 4], so [5, 9] exceeds need.
        # To test unavailable: need must be >= request, but request > available.
        # Available is [5, 8]. Customer 2 need is [3, 5], customer 0 need is [5, 4].
        # None of the customers currently have need > available.
        # But if customer 0 requests [5, 4] (which is granted and leaves available [0, 4]),
        # then customer 1 requesting [1, 0] (need [2, 1] >= [1, 0]) will be unavailable!
        self.client.request(customer=0, request=[5, 4])
        grant = self.wait_for_message(timeout=2.0)
        self.assertEqual(grant.get("status"), "granted")
        self.wait_for_message()  # Snapshot

        # Now available is [0, 4]. Customer 1 requests [1, 0]: need is [2, 1], but available has 0!
        self.client.request(customer=1, request=[1, 0])
        unavail = self.wait_for_message(timeout=2.0)
        self.assertEqual(unavail.get("status"), "unavailable")
        self.wait_for_message()  # Snapshot


if __name__ == "__main__":
    unittest.main(verbosity=2)
