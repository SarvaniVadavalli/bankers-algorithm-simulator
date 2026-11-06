"""
test_manual_mode.py: Comprehensive integration tests for Phase 5 Manual Resource Management Mode.

Tests:
1. Screen initialization (uninitialized state, clean widget rendering).
2. Dynamic customer selector populated from C backend snapshot.
3. Customer details update when selection changes (Maximum, Allocation, Need).
4. Dynamic resource input generation (exactly m entries generated for Request & Release).
5. Valid resource request granted (C backend status 'granted', safe sequence, updated matrices).
6. Request exceeding Need rejected (status 'exceeds_need', state unchanged).
7. Request exceeding Available rejected (status 'unavailable', state unchanged).
8. Unsafe request rejected without changing bank state (status 'unsafe', rollback verified).
9. Valid resource release (status 'released', Available increases, Allocation decreases).
10. Invalid release rejected (client-side & backend limit validation).
11. Backend snapshot synchronization (all matrices match C backend output).
12. Navigation and shared BackendClient identity between BankerApp, Dashboard, and ManualMode.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
import tkinter as tk
from typing import Callable, Optional

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from app import BankerApp
from manual_mode import ManualModeFrame
from styles import setup_styles


class TestManualMode(unittest.TestCase):
    """Integration test suite for Manual Resource Management Mode."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a hidden Tkinter root window for headless integration testing."""
        cls.root = tk.Tk()
        cls.root.withdraw()
        setup_styles(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        """Destroy the shared Tk root."""
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self) -> None:
        """Create fresh BackendClient and frame before each test."""
        self.client = BackendClient()
        self.client.start()
        self.frame: Optional[ManualModeFrame] = None
        self.app: Optional[BankerApp] = None

    def tearDown(self) -> None:
        """Clean up widgets and stop backend client."""
        if self.frame is not None and self.frame.winfo_exists():
            self.frame.pause_polling()
            self.frame.destroy()
            self.frame = None

        if self.app is not None:
            if self.app.dashboard_frame.winfo_exists():
                self.app.dashboard_frame.pause_polling()
                self.app.dashboard_frame.destroy()
            if self.app.configuration_frame.winfo_exists():
                self.app.configuration_frame.destroy()
            if self.app.manual_mode_frame.winfo_exists():
                self.app.manual_mode_frame.pause_polling()
                self.app.manual_mode_frame.destroy()
            if self.app.container.winfo_exists():
                self.app.container.destroy()
            self.app = None

        self.pump_events(2)

        if self.client.is_running():
            self.client.stop()

    def pump_events(self, iterations: int = 5, delay: float = 0.02) -> None:
        """Pump Tkinter event loop to process scheduled after() callbacks."""
        for _ in range(iterations):
            self.root.update_idletasks()
            self.root.update()
            time.sleep(delay)

    def wait_for(self, condition_fn: Callable[[], bool], timeout: float = 3.0) -> bool:
        """Poll Tkinter event loop until condition returns True or timeout expires."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pump_events(1, delay=0.02)
            if condition_fn():
                return True
        return False

    def init_classic_5x3(self) -> None:
        """Initialize backend with standard 5-customer, 3-resource dataset."""
        self.client.initialize(
            customers=5,
            resources=3,
            total=[10, 5, 7],
            maximum=[
                [7, 5, 3],
                [3, 2, 2],
                [9, 0, 2],
                [2, 2, 2],
                [4, 3, 3],
            ],
            allocation=[
                [0, 1, 0],
                [2, 0, 0],
                [3, 0, 2],
                [2, 1, 1],
                [0, 0, 2],
            ],
        )

    # =========================================================================
    # Test Cases
    # =========================================================================

    def test_01_screen_initialization(self) -> None:
        """Test 1: Screen renders gracefully in uninitialized state without crashing."""
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)
        self.pump_events(3)

        self.assertFalse(self.frame._is_initialized)
        self.assertIsNone(self.frame._current_snapshot)
        self.assertEqual(self.frame.badge_state.cget("text"), "Uninitialized")
        self.assertEqual(self.frame.lbl_safe_sequence.cget("text"), "—")
        self.assertEqual(list(self.frame.combo_customer["values"]), [])
        self.assertEqual(self.frame.lbl_cust_max.cget("text"), "[—]")

    def test_02_dynamic_customer_selector(self) -> None:
        """Test 2: Dynamic customer selector populated from C backend snapshot (e.g. 4 customers)."""
        # Initialize backend with 4 customers, 2 resources
        self.client.initialize(
            customers=4,
            resources=2,
            total=[10, 10],
            maximum=[[4, 4], [3, 3], [5, 5], [2, 2]],
            allocation=[[1, 1], [1, 1], [2, 2], [0, 0]],
        )

        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        # Wait for snapshot to be consumed
        self.assertTrue(self.wait_for(lambda: self.frame._is_initialized and self.frame._current_snapshot is not None))

        expected = ["Customer C0", "Customer C1", "Customer C2", "Customer C3"]
        self.assertEqual(list(self.frame.combo_customer["values"]), expected)
        self.assertEqual(self.frame.combo_customer.get(), "Customer C0")

    def test_03_customer_details_update_on_selection(self) -> None:
        """Test 3: Customer details (Max, Alloc, Need) update when customer selection changes."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Initially C0 is selected: Max=[7, 5, 3], Alloc=[0, 1, 0], Need=[7, 4, 3]
        self.assertEqual(self.frame.lbl_cust_max.cget("text"), "[7, 5, 3]")
        self.assertEqual(self.frame.lbl_cust_alloc.cget("text"), "[0, 1, 0]")
        self.assertEqual(self.frame.lbl_cust_need.cget("text"), "[7, 4, 3]")

        # Change selection to Customer C2: Max=[9, 0, 2], Alloc=[3, 0, 2], Need=[6, 0, 0]
        self.frame.combo_customer.current(2)
        self.frame.on_customer_selected()
        self.pump_events(2)

        self.assertEqual(self.frame._selected_customer_idx, 2)
        self.assertEqual(self.frame.lbl_cust_max.cget("text"), "[9, 0, 2]")
        self.assertEqual(self.frame.lbl_cust_alloc.cget("text"), "[3, 0, 2]")
        self.assertEqual(self.frame.lbl_cust_need.cget("text"), "[6, 0, 0]")

    def test_04_dynamic_resource_input_generation(self) -> None:
        """Test 4: Dynamic generation of m input entries for Request and Release forms."""
        # Initialize with 4 resource types
        self.client.initialize(
            customers=2,
            resources=4,
            total=[10, 10, 10, 10],
            maximum=[[3, 3, 3, 3], [2, 2, 2, 2]],
            allocation=[[1, 1, 1, 1], [0, 0, 0, 0]],
        )

        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: len(self.frame.req_entries) == 4))
        self.assertEqual(len(self.frame.req_entries), 4)
        self.assertEqual(len(self.frame.rel_entries), 4)

    def test_05_valid_resource_request_granted(self) -> None:
        """Test 5: Valid resource request is granted by C backend and updates state."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Select Customer C1: current Alloc=[2, 0, 0], Need=[1, 2, 2], Available=[3, 3, 2]
        self.frame.combo_customer.current(1)
        self.frame.on_customer_selected()

        # Enter valid request [1, 0, 2]
        for ent, val in zip(self.frame.req_entries, [1, 0, 2]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        # Submit request
        self.frame.submit_request()

        # Wait for request outcome and updated snapshot
        self.assertTrue(
            self.wait_for(
                lambda: "GRANTED" in self.frame.lbl_banner_title.cget("text")
                and self.frame._current_snapshot.get("available") == [2, 3, 0]
            )
        )

        # Verify C1 allocation increased to [3, 0, 2]
        self.assertEqual(self.frame._current_snapshot["allocation"][1], [3, 0, 2])
        # Verify C1 need decreased to [0, 2, 0]
        self.assertEqual(self.frame._current_snapshot["need"][1], [0, 2, 0])
        # Verify safe sequence displayed
        self.assertIn("C", self.frame.lbl_safe_sequence.cget("text"))

    def test_06_request_exceeding_need_rejected(self) -> None:
        """Test 6: Request exceeding declared Need is rejected by C backend."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Select C0: Need is [7, 4, 3]. Request [8, 0, 0] (> Need[0])
        self.frame.combo_customer.current(0)
        self.frame.on_customer_selected()

        for ent, val in zip(self.frame.req_entries, [8, 0, 0]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        self.frame.submit_request()

        self.assertTrue(
            self.wait_for(
                lambda: "EXCEEDS NEED" in self.frame.lbl_banner_title.cget("text")
            )
        )

        # State must remain completely unchanged
        self.assertEqual(self.frame._current_snapshot["available"], [3, 3, 2])
        self.assertEqual(self.frame._current_snapshot["allocation"][0], [0, 1, 0])

    def test_07_request_exceeding_available_rejected(self) -> None:
        """Test 7: Request exceeding Available pool is rejected by C backend."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Select C0: Need is [7, 4, 3], Available is [3, 3, 2].
        # Request [4, 0, 0]: <= Need, but 4 > Available[0] (3)
        self.frame.combo_customer.current(0)
        self.frame.on_customer_selected()

        for ent, val in zip(self.frame.req_entries, [4, 0, 0]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        self.frame.submit_request()

        self.assertTrue(
            self.wait_for(
                lambda: "RESOURCES UNAVAILABLE" in self.frame.lbl_banner_title.cget("text")
            )
        )

        # State must remain completely unchanged
        self.assertEqual(self.frame._current_snapshot["available"], [3, 3, 2])
        self.assertEqual(self.frame._current_snapshot["allocation"][0], [0, 1, 0])

    def test_08_unsafe_request_rejected_without_changing_bank_state(self) -> None:
        """Test 8: Unsafe request is rejected by C backend and tentative allocation rolled back."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # C0 requests [0, 3, 0].
        # [0, 3, 0] <= Need [7, 4, 3] and [0, 3, 0] <= Available [3, 3, 2].
        # But granting it leaves Available [3, 0, 2], causing potential deadlock!
        self.frame.combo_customer.current(0)
        self.frame.on_customer_selected()

        for ent, val in zip(self.frame.req_entries, [0, 3, 0]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        self.frame.submit_request()

        self.assertTrue(
            self.wait_for(
                lambda: "UNSAFE STATE" in self.frame.lbl_banner_title.cget("text")
            )
        )

        # Verify tentative allocation was rolled back: state is unchanged and safe!
        self.assertEqual(self.frame._current_snapshot["available"], [3, 3, 2])
        self.assertEqual(self.frame._current_snapshot["allocation"][0], [0, 1, 0])
        self.assertTrue(self.frame._current_snapshot["safe"])

    def test_09_valid_resource_release(self) -> None:
        """Test 9: Valid resource release updates available pool and allocation."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # C0 currently has allocation [0, 1, 0]. Release [0, 1, 0].
        self.frame.combo_customer.current(0)
        self.frame.on_customer_selected()

        for ent, val in zip(self.frame.rel_entries, [0, 1, 0]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        self.frame.submit_release()

        self.assertTrue(
            self.wait_for(
                lambda: "RELEASED" in self.frame.lbl_banner_title.cget("text")
                and self.frame._current_snapshot.get("available") == [3, 4, 2]
            )
        )

        # Allocation should now be [0, 0, 0]
        self.assertEqual(self.frame._current_snapshot["allocation"][0], [0, 0, 0])
        # Need should increase by released amount: [7, 4, 3] -> [7, 5, 3]
        self.assertEqual(self.frame._current_snapshot["need"][0], [7, 5, 3])

    def test_10_invalid_release_rejected(self) -> None:
        """Test 10: Attempting to release more than customer holds is rejected."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # C0 holds [0, 1, 0]. Attempt to release [0, 2, 0].
        self.frame.combo_customer.current(0)
        self.frame.on_customer_selected()

        for ent, val in zip(self.frame.rel_entries, [0, 2, 0]):
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

        self.frame.submit_release()

        self.assertTrue(
            self.wait_for(
                lambda: "Release Rejected" in self.frame.lbl_banner_title.cget("text")
            )
        )

        # Allocation and Available remain completely unchanged
        self.assertEqual(self.frame._current_snapshot["available"], [3, 3, 2])
        self.assertEqual(self.frame._current_snapshot["allocation"][0], [0, 1, 0])

    def test_11_backend_snapshot_synchronization(self) -> None:
        """Test 11: All displayed matrices and vectors match backend snapshot data exactly."""
        self.init_classic_5x3()
        self.frame = ManualModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        snap = self.frame._current_snapshot
        self.assertEqual(snap["customers"], 5)
        self.assertEqual(snap["resources"], 3)
        self.assertEqual(snap["available"], [3, 3, 2])
        self.assertTrue(snap["safe"])

        # Check that matrix cells rendered in UI match snapshot data
        alloc_labels = self.frame._matrix_labels["allocation"]
        self.assertEqual(len(alloc_labels), 5)
        for i in range(5):
            # cell 0 is row header label 'Ci'; cells 1..m are data cells
            row_vals = [int(lbl.cget("text")) for lbl in alloc_labels[i][1:]]
            self.assertEqual(row_vals, snap["allocation"][i])

        need_labels = self.frame._matrix_labels["need"]
        for i in range(5):
            row_vals = [int(lbl.cget("text")) for lbl in need_labels[i][1:]]
            self.assertEqual(row_vals, snap["need"][i])

    def test_12_navigation_and_shared_backend_client(self) -> None:
        """Test 12: Navigation between screens and shared BackendClient identity."""
        self.init_classic_5x3()
        self.app = BankerApp(root=self.root, client=self.client)
        self.pump_events(5)

        # Verify shared client identity across all 3 frames
        self.assertIs(self.app.dashboard_frame.client, self.client)
        self.assertIs(self.app.configuration_frame.client, self.client)
        self.assertIs(self.app.manual_mode_frame.client, self.client)

        # Start on dashboard
        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())

        # Navigate to Manual Mode
        self.app.dashboard_frame.navigate_to_manual()
        self.pump_events(5)

        self.assertEqual(self.app._current_screen, "manual_mode")
        self.assertIn(self.app.manual_mode_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.dashboard_frame, self.app.container.pack_slaves())

        # Verify state was preserved and snapshot refreshed
        self.assertTrue(
            self.wait_for(
                lambda: self.app.manual_mode_frame._current_snapshot is not None
                and self.app.manual_mode_frame._current_snapshot.get("available") == [3, 3, 2]
            )
        )

        # Navigate back to Dashboard
        self.app.manual_mode_frame.navigate_to_dashboard()
        self.pump_events(5)

        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.manual_mode_frame, self.app.container.pack_slaves())


if __name__ == "__main__":
    unittest.main()

