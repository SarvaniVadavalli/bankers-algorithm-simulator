"""
test_configuration.py: Unit and integration tests for ConfigurationFrame.

Tests:
- Initial screen rendering and default presets.
- Dynamic dimension updates and matrix re-generation.
- Input validation:
  - Negative values rejection.
  - Allocation exceeding Maximum claim rejection (Alloc[i][j] > Max[i][j]).
  - Sum of allocations exceeding Total instances rejection (Sum(Alloc[*][j]) > Total[j]).
  - Out of bounds dimension rejection (< 1 or > 50 customers, < 1 or > 10 resources).
- Real backend integration & Regression tests:
  - Successful initialization feedback and prominent success banner.
  - Displaying real backend snapshot (Available vector, Need matrix, Safety, Sequence).
  - Duplicate-click prevention while initialization is pending.
  - Button state transitions (disabled with 'Initializing...', re-enabled after completion).
  - Backend error feedback and error banner display.
  - Go to Dashboard navigation callback.
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock
import tkinter as tk

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from configuration import (
    ConfigurationFrame,
    MAX_CUSTOMERS,
    MAX_RESOURCES,
    MIN_CUSTOMERS,
    MIN_RESOURCES,
)
from styles import setup_styles


class TestConfigurationUI(unittest.TestCase):
    """Test suite for ConfigurationFrame and its integration with BackendClient."""

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
        """Create a fresh BackendClient and ConfigurationFrame before each test."""
        self.client = BackendClient()
        self.client.start()
        self.callback_init_mock = MagicMock()
        self.callback_dashboard_mock = MagicMock()
        self.config_frame = ConfigurationFrame(
            self.root,
            client=self.client,
            on_initialized=self.callback_init_mock,
            on_go_to_dashboard=self.callback_dashboard_mock,
        )
        self.config_frame.pack(fill="both", expand=True)
        self.pump_events(5)

    def tearDown(self) -> None:
        """Clean up frame and ensure backend process stops."""
        if self.config_frame.winfo_exists():
            self.config_frame.destroy()
        if self.client.is_running():
            self.client.stop()

    def pump_events(self, iterations: int = 5, delay: float = 0.02) -> None:
        """Process pending Tkinter events and polling callbacks."""
        for _ in range(iterations):
            self.root.update_idletasks()
            self.root.update()
            time.sleep(delay)

    def test_01_initial_screen_rendering(self) -> None:
        """Verify initial default screen rendering (5 customers, 3 resources)."""
        self.assertEqual(self.config_frame.customers_var.get(), "5")
        self.assertEqual(self.config_frame.resources_var.get(), "3")

        # Check entry counts
        self.assertEqual(len(self.config_frame.total_entries), 3)
        self.assertEqual(len(self.config_frame.maximum_entries), 5)
        self.assertEqual(len(self.config_frame.allocation_entries), 5)

        for row in self.config_frame.maximum_entries:
            self.assertEqual(len(row), 3)
        for row in self.config_frame.allocation_entries:
            self.assertEqual(len(row), 3)

        # Check default 5x3 preset total values
        self.assertEqual(self.config_frame.total_entries[0].get(), "10")
        self.assertEqual(self.config_frame.total_entries[1].get(), "5")
        self.assertEqual(self.config_frame.total_entries[2].get(), "7")

    def test_02_dynamic_dimension_changes_and_matrix_generation(self) -> None:
        """Verify dynamic matrix regeneration when dimensions change."""
        # Change to 4 customers and 2 resources
        self.config_frame.customers_var.set("4")
        self.config_frame.resources_var.set("2")
        self.config_frame.generate_matrix_from_inputs()
        self.pump_events(3)

        self.assertEqual(len(self.config_frame.total_entries), 2)
        self.assertEqual(len(self.config_frame.maximum_entries), 4)
        self.assertEqual(len(self.config_frame.allocation_entries), 4)

        for row in self.config_frame.maximum_entries:
            self.assertEqual(len(row), 2)
        for row in self.config_frame.allocation_entries:
            self.assertEqual(len(row), 2)

    def test_03_dimension_limits_validation(self) -> None:
        """Verify dimension constraints (1-50 customers, 1-10 resources)."""
        # Test 0 customers (invalid)
        self.config_frame.customers_var.set("0")
        self.config_frame.resources_var.set("3")
        self.config_frame.generate_matrix_from_inputs()
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("Customer count must be between", status_text)

        # Test 55 customers (exceeds max 50)
        self.config_frame.customers_var.set("55")
        self.config_frame.resources_var.set("3")
        self.config_frame.generate_matrix_from_inputs()
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("Customer count must be between", status_text)

        # Test 12 resources (exceeds max 10)
        self.config_frame.customers_var.set("5")
        self.config_frame.resources_var.set("12")
        self.config_frame.generate_matrix_from_inputs()
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("Resource type count must be between", status_text)

        # Test non-integer input
        self.config_frame.customers_var.set("abc")
        self.config_frame.resources_var.set("3")
        self.config_frame.generate_matrix_from_inputs()
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("must be positive integers", status_text)

    def test_04_negative_values_rejection(self) -> None:
        """Verify rejection of negative numbers in totals and matrices."""
        self.config_frame.load_preset_3x2()

        # Set negative total
        self.config_frame.total_entries[0].delete(0, tk.END)
        self.config_frame.total_entries[0].insert(0, "-5")
        res = self.config_frame.validate_and_collect_data()
        self.assertIsNone(res)
        self.assertIn("must be between 0 and 1000", self.config_frame.lbl_status.cget("text"))

        # Restore total, set negative allocation
        self.config_frame.total_entries[0].delete(0, tk.END)
        self.config_frame.total_entries[0].insert(0, "10")
        self.config_frame.allocation_entries[0][0].delete(0, tk.END)
        self.config_frame.allocation_entries[0][0].insert(0, "-1")
        res = self.config_frame.validate_and_collect_data()
        self.assertIsNone(res)
        self.assertIn("cannot be negative", self.config_frame.lbl_status.cget("text"))

    def test_05_allocation_exceeding_maximum_rejection(self) -> None:
        """Verify rejection when an allocation exceeds customer maximum claim."""
        self.config_frame.load_preset_3x2()

        # For Customer C0, Resource R0: Maximum is 7. Set Allocation to 8.
        self.config_frame.maximum_entries[0][0].delete(0, tk.END)
        self.config_frame.maximum_entries[0][0].insert(0, "7")
        self.config_frame.allocation_entries[0][0].delete(0, tk.END)
        self.config_frame.allocation_entries[0][0].insert(0, "8")

        res = self.config_frame.validate_and_collect_data()
        self.assertIsNone(res)
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("exceeds Maximum claim", status_text)
        self.assertIn("C0, R0", status_text)

    def test_06_allocation_exceeding_total_rejection(self) -> None:
        """Verify rejection when the sum of allocations for a resource exceeds its total."""
        self.config_frame.load_preset_3x2()

        # Total for R0 is 10.
        # Set Maximums large enough so Alloc <= Max holds:
        for i in range(3):
            self.config_frame.maximum_entries[i][0].delete(0, tk.END)
            self.config_frame.maximum_entries[i][0].insert(0, "6")
            self.config_frame.allocation_entries[i][0].delete(0, tk.END)
            self.config_frame.allocation_entries[i][0].insert(0, "4")

        # Sum of allocations for R0 is 4 + 4 + 4 = 12 > 10!
        res = self.config_frame.validate_and_collect_data()
        self.assertIsNone(res)
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("exceed Total existing instances", status_text)
        self.assertIn("R0", status_text)

    def test_07_successful_initialization_feedback_and_snapshot_display(self) -> None:
        """
        Verify:
        - Successful initialization displays green success banner with metrics.
        - Section 4 displays backend-calculated Need matrix, Available pool, and Safe sequence.
        - Parent callbacks are properly invoked.
        """
        self.config_frame.load_preset_3x2()

        # Submit initialization
        self.config_frame.initialize_bank()
        self.assertTrue(self.config_frame.is_pending())

        # Pump events until backend responds and after() handler processes it
        deadline = time.time() + 4.0
        while time.time() < deadline:
            self.pump_events(2)
            if not self.config_frame.is_pending():
                break

        # Verification: Not pending and button re-enabled
        self.assertFalse(self.config_frame.is_pending())
        self.assertEqual(self.config_frame.btn_init.cget("text"), "Re-initialize Bank")

        # Verification: Banner status text and details
        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("Bank initialized successfully", status_text)
        self.assertIn("SAFE STATE", status_text)

        details_text = self.config_frame.lbl_banner_details.cget("text")
        self.assertIn("3 Customers, 2 Resources", details_text)
        self.assertIn("Available Pool: [5, 8]", details_text)
        self.assertIn("Safe Sequence", details_text)

        # Verification: Section 4 Need Matrix is displayed
        self.assertTrue(self.config_frame.results_section_frame.winfo_ismapped())
        need_matrix = self.config_frame._last_snapshot.get("need")  # [[5, 4], [2, 1], [3, 5]]
        self.assertEqual(need_matrix, [[5, 4], [2, 1], [3, 5]])

        # Verification: Navigation callbacks
        self.callback_init_mock.assert_called_once()
        snapshot = self.callback_init_mock.call_args[0][0]
        self.assertEqual(snapshot.get("customers"), 3)
        self.assertEqual(snapshot.get("resources"), 2)
        self.assertEqual(snapshot.get("available"), [5, 8])

        # Test clicking "Go to Dashboard"
        self.config_frame.go_to_dashboard()
        self.callback_dashboard_mock.assert_called_once()

    def test_08_duplicate_click_prevention_and_button_reenable(self) -> None:
        """
        Regression test:
        - Verify button disables and text changes to 'Initializing...' while pending.
        - Verify duplicate clicks while pending are ignored.
        - Verify button re-enables to 'Re-initialize Bank' upon completion.
        """
        self.config_frame.load_preset_3x2()

        # Click 1: Start initialization
        self.config_frame.initialize_bank()
        self.assertTrue(self.config_frame.is_pending())
        self.assertEqual(self.config_frame.btn_init.cget("text"), "Initializing...")
        self.assertIn("disabled", str(self.config_frame.btn_init.state()))

        # Click 2 & Click 3: Immediate duplicate clicks while in-flight
        self.config_frame.initialize_bank()
        self.config_frame.initialize_bank()

        # Still pending, text unchanged
        self.assertTrue(self.config_frame.is_pending())
        self.assertEqual(self.config_frame.btn_init.cget("text"), "Initializing...")

        # Wait for completion
        deadline = time.time() + 4.0
        while time.time() < deadline:
            self.pump_events(2)
            if not self.config_frame.is_pending():
                break

        self.assertFalse(self.config_frame.is_pending())
        self.assertEqual(self.config_frame.btn_init.cget("text"), "Re-initialize Bank")
        self.assertNotIn("disabled", str(self.config_frame.btn_init.state()))

    def test_09_backend_error_feedback(self) -> None:
        """
        Regression test:
        - Verify backend errors are caught and rendered in a prominent red banner.
        - Verify results section is hidden on error.
        - Verify Initialize button is re-enabled with 'Initialize Bank'.
        """
        self.config_frame.load_preset_3x2()

        # Simulate backend error response in the queue handler
        error_msg = {"status": "error", "message": "Backend memory allocation failure simulated"}
        self.config_frame._init_pending = True
        self.config_frame.btn_init.configure(state="disabled", text="Initializing...")

        # Feed error message into client queue and trigger check
        self.client._queue.put(error_msg)
        self.config_frame._check_init_response()

        # Verify error handling
        self.assertFalse(self.config_frame.is_pending())
        self.assertEqual(self.config_frame.btn_init.cget("text"), "Initialize Bank")
        self.assertNotIn("disabled", str(self.config_frame.btn_init.state()))

        status_text = self.config_frame.lbl_status.cget("text")
        self.assertIn("Backend rejected configuration", status_text)
        self.assertIn("Backend memory allocation failure simulated", status_text)

        # Section 4 should remain hidden
        self.assertFalse(self.config_frame.results_section_frame.winfo_ismapped())


if __name__ == "__main__":
    unittest.main(verbosity=2)
