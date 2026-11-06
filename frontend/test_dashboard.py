"""
test_dashboard.py: Automated tests for DashboardFrame UI logic and backend integration.

Tests:
- DashboardFrame instantiation with dark theme.
- Graceful handling of uninitialized state.
- Real backend data synchronization via after() polling loop.
- Summary cards update (customers, resources, available pool, safety status).
- Resource availability bar generation.
- Activity feed event logging.
"""

from __future__ import annotations

import time
import unittest
from pathlib import Path
import tkinter as tk

# Ensure frontend directory is importable
import sys

FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from styles import setup_styles
from dashboard import DashboardFrame


class TestDashboardUI(unittest.TestCase):
    """Test suite for DashboardFrame and BackendClient integration."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a hidden Tkinter root window."""
        cls.root = tk.Tk()
        cls.root.withdraw()  # Run headless without opening visible window
        setup_styles(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        """Destroy the Tkinter root window."""
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self) -> None:
        """Start fresh BackendClient and DashboardFrame for each test."""
        self.client = BackendClient()
        self.client.start()
        self.dashboard = DashboardFrame(self.root, client=self.client)
        self.dashboard.pack(fill="both", expand=True)
        self.pump_events(10)

    def tearDown(self) -> None:
        """Clean up dashboard and client."""
        if self.dashboard.winfo_exists():
            self.dashboard.destroy()
        if self.client.is_running():
            self.client.stop()

    def pump_events(self, iterations: int = 5, delay: float = 0.02) -> None:
        """Process pending Tkinter events and polling callbacks."""
        for _ in range(iterations):
            self.root.update_idletasks()
            self.root.update()
            time.sleep(delay)

    def test_01_initial_uninitialized_state(self) -> None:
        """Verify dashboard starts gracefully in uninitialized state without crashing."""
        self.assertEqual(self.dashboard.lbl_cust_val.cget("text"), "—")
        self.assertEqual(self.dashboard.lbl_res_val.cget("text"), "—")
        self.assertEqual(self.dashboard.lbl_avail_val.cget("text"), "—")
        self.assertIn("UNINITIALIZED", self.dashboard.lbl_safety_val.cget("text"))
        self.assertEqual(self.dashboard.badge_state.cget("text"), "Uninitialized")

    def test_02_real_backend_data_update(self) -> None:
        """
        Verify dashboard updates summary cards and resource bars
        when real backend initialization and snapshot data arrives.
        """
        # Load demo preset (5 customers, 3 resources)
        self.dashboard.load_demo_preset()

        # Wait up to 3 seconds for backend response and queue polling
        deadline = time.time() + 3.0
        while time.time() < deadline:
            self.pump_events(2)
            if self.dashboard._is_initialized and self.dashboard.lbl_cust_val.cget("text") == "5":
                break

        # Check KPI summary cards
        self.assertEqual(self.dashboard.lbl_cust_val.cget("text"), "5")
        self.assertEqual(self.dashboard.lbl_res_val.cget("text"), "3")
        self.assertEqual(self.dashboard.lbl_avail_val.cget("text"), "[3, 3, 2]")
        self.assertIn("SAFE", self.dashboard.lbl_safety_val.cget("text"))
        self.assertEqual(self.dashboard.badge_state.cget("text"), "System Active")

        # Check resource availability bars were generated for R0, R1, R2
        child_rows = self.dashboard.res_content_frame.winfo_children()
        self.assertEqual(len(child_rows), 3, "Expected 3 resource rows for 3 resources")

        # Check activity feed logged INIT and SNAPSHOT
        log_text = self.dashboard.txt_log.get("1.0", tk.END)
        self.assertIn("INIT", log_text)
        self.assertIn("SNAPSHOT", log_text)

    def test_03_refresh_and_clear_activity(self) -> None:
        """Test refreshing snapshot and clearing the activity log."""
        self.dashboard.load_demo_preset()
        self.pump_events(15)

        # Activity log should have entries
        self.assertGreater(self.dashboard._event_counter, 0)

        # Clear log
        self.dashboard.clear_activity_log()
        self.assertEqual(self.dashboard._event_counter, 0)
        self.assertEqual(self.dashboard.txt_log.get("1.0", tk.END).strip(), "")

        # Request fresh snapshot
        self.dashboard.refresh_snapshot()
        self.pump_events(10)
        self.assertGreater(self.dashboard._event_counter, 0)
        log_after = self.dashboard.txt_log.get("1.0", tk.END)
        self.assertIn("SNAPSHOT", log_after)


if __name__ == "__main__":
    unittest.main(verbosity=2)

