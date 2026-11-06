"""
test_navigation.py: Integration tests for application-level navigation and screen management.

Tests:
- Shared BackendClient identity between ApplicationController, DashboardFrame, and ConfigurationFrame.
- Navigation from Dashboard to Configuration via "Configure System".
- Navigation from Configuration to Dashboard via "Go to Dashboard" (enforcing initialization prerequisite).
- Seamless screen transitions (showing/hiding frames without destroying them).
- Automatic dashboard snapshot refresh when becoming visible.
- Preservation of backend state and configuration form data across screen transitions.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
import tkinter as tk

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from app import BankerApp
from styles import setup_styles


class TestNavigation(unittest.TestCase):
    """Integration test suite for screen navigation and state preservation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Create a hidden Tkinter root window for headless testing."""
        cls.root = tk.Tk()
        cls.root.withdraw()
        setup_styles(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        """Destroy the Tkinter root window."""
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self) -> None:
        """Create a fresh BackendClient and BankerApp before each test."""
        self.client = BackendClient()
        self.client.start()
        self.app = BankerApp(root=self.root, client=self.client)
        self.pump_events(5)

    def tearDown(self) -> None:
        """Clean up frames and terminate backend client."""
        if hasattr(self, "app"):
            if self.app.dashboard_frame.winfo_exists():
                self.app.dashboard_frame.pause_polling()
                self.app.dashboard_frame.destroy()
            if self.app.configuration_frame.winfo_exists():
                self.app.configuration_frame.destroy()
            if hasattr(self.app, "manual_mode_frame") and self.app.manual_mode_frame.winfo_exists():
                self.app.manual_mode_frame.pause_polling()
                self.app.manual_mode_frame.destroy()
            if hasattr(self.app, "automatic_mode_frame") and self.app.automatic_mode_frame.winfo_exists():
                self.app.automatic_mode_frame.pause_polling()
                self.app.automatic_mode_frame.destroy()
            if self.app.container.winfo_exists():
                self.app.container.destroy()
        if self.client.is_running():
            self.client.stop()

    def pump_events(self, iterations: int = 5, delay: float = 0.02) -> None:
        """Process pending Tkinter events and polling callbacks."""
        for _ in range(iterations):
            self.root.update_idletasks()
            self.root.update()
            time.sleep(delay)

    def test_01_shared_backend_client_identity(self) -> None:
        """Verify that BankerApp, DashboardFrame, ConfigurationFrame, ManualModeFrame, and AutomaticModeFrame share the exact same BackendClient."""
        self.assertIs(self.app.client, self.client)
        self.assertIs(self.app.dashboard_frame.client, self.client)
        self.assertIs(self.app.configuration_frame.client, self.client)
        self.assertIs(self.app.manual_mode_frame.client, self.client)
        self.assertIs(self.app.automatic_mode_frame.client, self.client)
        self.assertIs(self.app.dashboard_frame.client, self.app.configuration_frame.client)
        self.assertIs(self.app.dashboard_frame.client, self.app.manual_mode_frame.client)
        self.assertIs(self.app.dashboard_frame.client, self.app.automatic_mode_frame.client)

    def test_02_dashboard_to_configuration_navigation(self) -> None:
        """Verify navigating from Dashboard to Configuration using 'Configure System'."""
        self.app.show_dashboard()
        self.pump_events(3)
        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.configuration_frame, self.app.container.pack_slaves())

        # Trigger navigation to Configuration
        self.app.dashboard_frame.navigate_to_configuration()
        self.pump_events(3)

        self.assertEqual(self.app._current_screen, "configuration")
        self.assertIn(self.app.configuration_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.dashboard_frame, self.app.container.pack_slaves())

    def test_03_configuration_to_dashboard_requires_initialization(self) -> None:
        """Verify that 'Go to Dashboard' blocks navigation if bank is not yet initialized."""
        # Switch to configuration with clean uninitialized state
        self.client.reset()
        self.pump_events(3)
        self.app.configuration_frame._last_snapshot = None
        self.app.show_configuration()
        self.pump_events(3)

        self.assertEqual(self.app._current_screen, "configuration")

        # Attempt to navigate to Dashboard before initializing
        self.app.configuration_frame.go_to_dashboard()
        self.pump_events(3)

        # Should remain on configuration screen and show warning
        self.assertEqual(self.app._current_screen, "configuration")
        self.assertIn(self.app.configuration_frame, self.app.container.pack_slaves())
        self.assertIn(
            "Please initialize the bank successfully",
            self.app.configuration_frame.lbl_status.cget("text"),
        )

    def test_04_configuration_to_dashboard_navigation_after_initialization(self) -> None:
        """Verify navigating from Configuration to Dashboard after successful initialization."""
        self.app.show_configuration()
        self.pump_events(3)

        # Load 3x2 preset and initialize bank
        self.app.configuration_frame.load_preset_3x2()
        self.app.configuration_frame.initialize_bank()

        # Wait for initialization to complete
        deadline = time.time() + 4.0
        while time.time() < deadline:
            self.pump_events(2)
            if not self.app.configuration_frame.is_pending():
                break

        self.assertFalse(self.app.configuration_frame.is_pending())
        self.assertIsNotNone(self.app.configuration_frame._last_snapshot)

        # Trigger Go to Dashboard
        self.app.configuration_frame.go_to_dashboard()
        self.pump_events(3)

        self.assertEqual(self.app._current_screen, "dashboard")
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertNotIn(self.app.configuration_frame, self.app.container.pack_slaves())

    def test_05_preserving_initialized_state_and_refreshing_dashboard(self) -> None:
        """
        Verify that after initialization and navigation:
        1. Dashboard refreshes its snapshot automatically.
        2. Dashboard displays the initialized state (customers, resources, available pool).
        3. Navigating back to Configuration preserves all form entries.
        4. Navigating back to Dashboard maintains active state without resetting.
        """
        self.app.show_configuration()
        self.pump_events(3)

        # Initialize with 3 customers and 2 resources
        self.app.configuration_frame.load_preset_3x2()
        self.app.configuration_frame.initialize_bank()

        deadline = time.time() + 4.0
        while time.time() < deadline:
            self.pump_events(2)
            if not self.app.configuration_frame.is_pending():
                break

        # Navigate to Dashboard
        self.app.show_dashboard()

        # Wait for dashboard to refresh snapshot
        deadline = time.time() + 3.0
        while time.time() < deadline:
            self.pump_events(2)
            if self.app.dashboard_frame._is_initialized and self.app.dashboard_frame.lbl_cust_val.cget("text") == "3":
                break

        # 1. Verify Dashboard updated with initialized values
        self.assertTrue(self.app.dashboard_frame._is_initialized)
        self.assertEqual(self.app.dashboard_frame.lbl_cust_val.cget("text"), "3")
        self.assertEqual(self.app.dashboard_frame.lbl_res_val.cget("text"), "2")
        self.assertEqual(self.app.dashboard_frame.lbl_avail_val.cget("text"), "[5, 8]")
        self.assertIn("SAFE", self.app.dashboard_frame.lbl_safety_val.cget("text"))

        # 2. Navigate back to Configuration
        self.app.show_configuration()
        self.pump_events(3)
        self.assertIn(self.app.configuration_frame, self.app.container.pack_slaves())

        # Verify Configuration form values are still intact
        self.assertEqual(self.app.configuration_frame.customers_var.get(), "3")
        self.assertEqual(self.app.configuration_frame.resources_var.get(), "2")
        self.assertEqual(self.app.configuration_frame.total_entries[0].get(), "10")
        self.assertEqual(self.app.configuration_frame.total_entries[1].get(), "10")

        # 3. Navigate back to Dashboard
        self.app.show_dashboard()
        self.pump_events(3)
        self.assertIn(self.app.dashboard_frame, self.app.container.pack_slaves())
        self.assertEqual(self.app.dashboard_frame.lbl_cust_val.cget("text"), "3")
        self.assertTrue(self.client.is_running())


if __name__ == "__main__":
    unittest.main(verbosity=2)
