"""
test_automatic_mode.py: Comprehensive integration tests for Phase 6 Automatic Resource Simulation Mode.

Tests:
1. Screen initialization (uninitialized state, clean widget rendering).
2. Dynamic request input generation (N rows by M columns generated dynamically).
3. Quick preset actions (Fill Max Need, Zero All).
4. Valid automatic simulation execution using C backend's 'start_auto' command.
5. Backend event handling and thread monitoring (live POSIX thread states).
6. Resource state synchronization (post-simulation snapshot updates UI).
7. Prevention of multiple simultaneous simulation starts.
8. Error handling for uninitialized bank and invalid inputs.
9. Safe handling of Stop Simulation button.
10. Navigation between Dashboard and Automatic Mode.
11. Navigation between Manual Mode and Automatic Mode.
12. Shared BackendClient identity across BankerApp and all screens.
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
from automatic_mode import AutomaticModeFrame
from styles import setup_styles


class TestAutomaticMode(unittest.TestCase):
    """Integration test suite for Automatic Resource Simulation Mode."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create hidden Tkinter root window for headless integration testing."""
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
        """Create fresh BackendClient and frames before each test."""
        self.client = BackendClient()
        self.client.start()
        self.frame: Optional[AutomaticModeFrame] = None
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
            if self.app.automatic_mode_frame.winfo_exists():
                self.app.automatic_mode_frame.pause_polling()
                self.app.automatic_mode_frame.destroy()
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

    def wait_for(self, condition_fn: Callable[[], bool], timeout: float = 8.0) -> bool:
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
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)
        self.pump_events(3)

        self.assertFalse(self.frame._is_initialized)
        self.assertIsNone(self.frame._current_snapshot)
        self.assertFalse(self.frame._is_simulating)
        self.assertEqual(self.frame.badge_state.cget("text"), "Uninitialized")
        self.assertEqual(self.frame.badge_sim.cget("text"), "● Idle")
        self.assertEqual(self.frame.lbl_dim_val.cget("text"), "— Customers, — Resources")
        self.assertEqual(len(self.frame._req_entries), 0)
        self.assertEqual(len(self.frame._thread_cards), 0)

    def test_02_dynamic_request_input_generation(self) -> None:
        """Test 2: Dynamic generation of N x M entry grid matching configured dimensions."""
        # Initialize backend with 4 customers and 2 resources
        self.client.initialize(
            customers=4,
            resources=2,
            total=[10, 10],
            maximum=[[4, 4], [3, 3], [5, 5], [2, 2]],
            allocation=[[1, 1], [1, 1], [2, 2], [0, 0]],
        )

        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Check N x M grid
        self.assertEqual(len(self.frame._req_entries), 4)
        for row in self.frame._req_entries:
            self.assertEqual(len(row), 2)

        # Check thread monitoring tiles count
        self.assertEqual(len(self.frame._thread_cards), 4)
        self.assertEqual(self.frame.lbl_dim_val.cget("text"), "4 Customers, 2 Resource Types")

    def test_03_quick_preset_actions(self) -> None:
        """Test 3: Quick preset buttons (Fill Max Need, Zero All)."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # 1. Fill Maximum Need
        self.frame.fill_requests_with_need()
        need = self.frame._current_snapshot["need"]

        for i, row in enumerate(self.frame._req_entries):
            row_vals = [int(ent.get()) for ent in row]
            self.assertEqual(row_vals, need[i])

        # 2. Zero Out All
        self.frame.clear_request_inputs()
        for row in self.frame._req_entries:
            for ent in row:
                self.assertEqual(ent.get(), "0")

    def test_04_valid_automatic_simulation_execution(self) -> None:
        """Test 4: Valid automatic simulation executes via C backend 'start_auto'."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Set requests for all 5 customers:
        # C0: [1, 0, 0] (Need is [7, 4, 3])
        # C1: [1, 0, 0] (Need is [1, 2, 2])
        # C2: [1, 0, 0] (Need is [6, 0, 0])
        # C3: [0, 1, 0] (Need is [0, 1, 1])
        # C4: [0, 0, 1] (Need is [4, 3, 1])
        sample_requests = [
            [1, 0, 0],
            [1, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1],
        ]
        for i, req in enumerate(sample_requests):
            for j, val in enumerate(req):
                self.frame._req_entries[i][j].delete(0, tk.END)
                self.frame._req_entries[i][j].insert(0, str(val))

        # Start simulation
        self.frame.start_simulation()
        self.assertTrue(self.frame._is_simulating)
        self.assertEqual(self.frame.btn_start.cget("text"), "Simulating...")

        # Wait for simulation to finish (customer threads sleep 500ms and join)
        self.assertTrue(
            self.wait_for(
                lambda: not self.frame._is_simulating
                and "SIMULATION COMPLETE" in self.frame.lbl_banner_title.cget("text"),
                timeout=8.0,
            )
        )

        self.assertEqual(self.frame.btn_start.cget("text"), "Start Simulation")
        self.assertEqual(self.frame.badge_sim.cget("text"), "● Completed")

    def test_05_backend_event_handling_and_thread_monitoring(self) -> None:
        """Test 5: Live thread monitor accurately tracks POSIX thread events from C backend."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Set modest requests and execute
        self.frame.fill_requests_safe_baseline()
        self.frame.start_simulation()

        # Wait for completion
        self.assertTrue(
            self.wait_for(lambda: not self.frame._is_simulating, timeout=8.0)
        )

        # Verify all 5 threads have recorded states without any invented states
        self.assertEqual(len(self.frame._thread_states), 5)
        for i in range(5):
            state_info = self.frame._thread_states[i]
            self.assertIn(state_info["state"], ("COMPLETED", "REJECTED"))

        # Check log contains protocol events
        log_text = self.frame.txt_log.get("1.0", tk.END)
        self.assertIn("START", log_text)
        self.assertIn("AUTO", log_text)
        self.assertIn("COMPLETE", log_text)

    def test_06_resource_state_synchronization(self) -> None:
        """Test 6: Final snapshot from C backend synchronizes Available pool and safety status."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Run simulation where granted requests are released back to pool
        self.frame.fill_requests_safe_baseline()
        self.frame.start_simulation()

        self.assertTrue(
            self.wait_for(lambda: not self.frame._is_simulating, timeout=8.0)
        )

        # Backend snapshot after all threads release should have Available pool restored
        snap = self.frame._current_snapshot
        self.assertIsNotNone(snap)
        self.assertEqual(snap["customers"], 5)
        self.assertEqual(snap["resources"], 3)
        self.assertTrue(snap["safe"])
        self.assertEqual(snap["available"], [3, 3, 2])

    def test_07_prevent_multiple_simultaneous_starts(self) -> None:
        """Test 7: Prevent duplicate simulation calls while one is already in progress."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        self.frame.fill_requests_safe_baseline()
        self.frame.start_simulation()
        self.assertTrue(self.frame._is_simulating)

        # Attempt to start again while running: should be safely ignored
        self.frame.start_simulation()
        self.assertTrue(self.frame._is_simulating)

        # Wait for completion
        self.assertTrue(
            self.wait_for(lambda: not self.frame._is_simulating, timeout=8.0)
        )

    def test_08_error_handling_uninitialized_and_invalid_inputs(self) -> None:
        """Test 8: Error feedback for uninitialized bank and invalid/negative quantities."""
        # 1. Uninitialized bank
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)
        self.pump_events(2)

        self.frame.start_simulation()
        self.assertFalse(self.frame._is_simulating)
        self.assertIn("not initialized", self.frame.lbl_banner_title.cget("text").lower())

        # 2. Initialized bank with negative input
        self.init_classic_5x3()
        self.pump_events(5)
        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # Put invalid negative value in C0, R0
        self.frame._req_entries[0][0].delete(0, tk.END)
        self.frame._req_entries[0][0].insert(0, "-5")

        self.frame.start_simulation()
        self.assertFalse(self.frame._is_simulating)
        self.assertIn("nonnegative", self.frame.lbl_banner_title.cget("text").lower())

    def test_09_stop_simulation_safe_handling(self) -> None:
        """Test 9: Stop Simulation button provides safe explanation without corrupting backend."""
        self.init_classic_5x3()
        self.frame = AutomaticModeFrame(self.root, client=self.client)
        self.frame.pack(fill="both", expand=True)

        self.assertTrue(self.wait_for(lambda: self.frame._current_snapshot is not None))

        # When idle:
        self.frame.stop_simulation()
        self.assertIn("No simulation", self.frame.lbl_banner_title.cget("text"))

        # When running:
        self.frame.fill_requests_safe_baseline()
        self.frame.start_simulation()
        self.assertTrue(self.frame._is_simulating)

        self.frame.stop_simulation()
        self.assertIn("Stop Requested", self.frame.lbl_banner_title.cget("text"))

        # Must cleanly finish without crashing
        self.assertTrue(
            self.wait_for(lambda: not self.frame._is_simulating, timeout=8.0)
        )

    def test_10_navigation_between_dashboard_and_automatic_mode(self) -> None:
        """Test 10: Seamless navigation between Dashboard and Automatic Mode."""
        self.init_classic_5x3()
        self.app = BankerApp(root=self.root, client=self.client)
        self.pump_events(5)

        # Starts on Dashboard
        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.automatic_mode_frame, self.app.container.pack_slaves())

        # Navigate to Automatic Mode
        self.app.dashboard_frame.navigate_to_automatic()
        self.pump_events(5)

        self.assertEqual(self.app._current_screen, "automatic_mode")
        self.assertIn(self.app.automatic_mode_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.dashboard_frame, self.app.container.pack_slaves())

        # Navigate back to Dashboard
        self.app.automatic_mode_frame.navigate_to_dashboard()
        self.pump_events(5)

        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.automatic_mode_frame, self.app.container.pack_slaves())

    def test_11_navigation_between_manual_mode_and_automatic_mode(self) -> None:
        """Test 11: Direct navigation between Manual Mode and Automatic Mode."""
        self.init_classic_5x3()
        self.app = BankerApp(root=self.root, client=self.client)
        self.pump_events(5)

        # Go to Manual Mode
        self.app.show_manual_mode()
        self.pump_events(5)
        self.assertEqual(self.app._current_screen, "manual_mode")
        self.assertIn(self.app.manual_mode_frame, self.app.container.pack_slaves())

        # Switch to Automatic Mode
        self.app.manual_mode_frame.navigate_to_automatic()
        self.pump_events(5)
        self.assertEqual(self.app._current_screen, "automatic_mode")
        self.assertIn(self.app.automatic_mode_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.manual_mode_frame, self.app.container.pack_slaves())

        # Switch back to Manual Mode
        self.app.automatic_mode_frame.navigate_to_manual()
        self.pump_events(5)
        self.assertEqual(self.app._current_screen, "manual_mode")
        self.assertIn(self.app.manual_mode_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.automatic_mode_frame, self.app.container.pack_slaves())

    def test_12_shared_backend_client_identity(self) -> None:
        """Test 12: Shared BackendClient identity across BankerApp and all screens."""
        self.app = BankerApp(root=self.root, client=self.client)
        self.pump_events(3)

        self.assertIs(self.app.client, self.client)
        self.assertIs(self.app.dashboard_frame.client, self.client)
        self.assertIs(self.app.configuration_frame.client, self.client)
        self.assertIs(self.app.manual_mode_frame.client, self.client)
        self.assertIs(self.app.automatic_mode_frame.client, self.client)


if __name__ == "__main__":
    unittest.main()
