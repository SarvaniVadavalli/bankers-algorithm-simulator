"""
app.py: Central application controller managing screens, navigation, and shared BackendClient.

Manages:
- Single Tk root window with dark theme styling.
- Single shared BackendClient instance across all application screens.
- Seamless navigation between DashboardFrame and ConfigurationFrame.
- State preservation across screen transitions.
- Graceful shutdown of backend process on exit.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path
from typing import Optional

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from automatic_mode import AutomaticModeFrame
from configuration import ConfigurationFrame
from dashboard import DashboardFrame
from manual_mode import ManualModeFrame
from styles import BG_MAIN, setup_styles

logger = logging.getLogger("bankers.app")


class BankerApp:
    """
    Central Tkinter Application Controller.

    Manages:
    - Root Tk window lifecycle and graceful process termination.
    - Single shared BackendClient instance across all application screens.
    - Application dark theme styling.
    - Navigation between DashboardFrame and ConfigurationFrame.
    - Preservation of backend and UI state during screen transitions.
    """

    def __init__(
        self,
        root: Optional[tk.Tk] = None,
        client: Optional[BackendClient] = None,
    ) -> None:
        # 1. Manage Tk root window
        self._owns_root = root is None
        self.root = root if root is not None else tk.Tk()
        self.root.title("Banker's Algorithm Resource Management Simulator")
        self.root.geometry("1100x750")
        self.root.minsize(960, 620)

        # 2. Apply theme
        setup_styles(self.root)

        # 3. Initialize single shared BackendClient
        self._owns_client = client is None
        self.client = client if client is not None else BackendClient()
        if not self.client.is_running():
            try:
                self.client.start()
                logger.info(
                    "Shared BackendClient started (PID: %s)",
                    getattr(self.client._process, "pid", "?"),
                )
            except Exception as e:
                logger.error("Failed to start BackendClient: %s", e)

        # 4. Main container for screen swapping
        self.container = tk.Frame(self.root, bg=BG_MAIN)
        self.container.pack(fill="both", expand=True)

        # 5. Instantiate screens with shared client and navigation callbacks
        self.dashboard_frame = DashboardFrame(
            self.container,
            client=self.client,
            on_navigate_configuration=self.show_configuration,
            on_navigate_manual=self.show_manual_mode,
            on_navigate_automatic=self.show_automatic_mode,
        )

        self.configuration_frame = ConfigurationFrame(
            self.container,
            client=self.client,
            on_navigate_dashboard=self.show_dashboard,
        )

        self.manual_mode_frame = ManualModeFrame(
            self.container,
            client=self.client,
            on_navigate_dashboard=self.show_dashboard,
            on_navigate_automatic=self.show_automatic_mode,
        )

        self.automatic_mode_frame = AutomaticModeFrame(
            self.container,
            client=self.client,
            on_navigate_dashboard=self.show_dashboard,
            on_navigate_manual=self.show_manual_mode,
        )

        self._current_screen: Optional[str] = None

        # Start on dashboard by default
        self.show_dashboard()

        # Handle window close cleanly
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def show_dashboard(self) -> None:
        """
        Navigate to the Dashboard screen.

        Hides other frames and refreshes the Dashboard snapshot from the backend.
        """
        if self._current_screen == "dashboard":
            self.dashboard_frame.on_show()
            return

        self.configuration_frame.pack_forget()
        self.manual_mode_frame.pause_polling()
        self.manual_mode_frame.pack_forget()
        self.automatic_mode_frame.pause_polling()
        self.automatic_mode_frame.pack_forget()

        self._current_screen = "dashboard"
        self.dashboard_frame.pack(fill="both", expand=True)
        self.dashboard_frame.on_show()

    def show_configuration(self) -> None:
        """
        Navigate to the Dynamic Configuration screen.

        Pauses Dashboard, Manual, and Automatic Mode polling and presents ConfigurationFrame.
        """
        if self._current_screen == "configuration":
            return

        self.dashboard_frame.pause_polling()
        self.dashboard_frame.pack_forget()
        self.manual_mode_frame.pause_polling()
        self.manual_mode_frame.pack_forget()
        self.automatic_mode_frame.pause_polling()
        self.automatic_mode_frame.pack_forget()

        self._current_screen = "configuration"
        self.configuration_frame.pack(fill="both", expand=True)

    def show_manual_mode(self) -> None:
        """
        Navigate to the Manual Resource Management Mode screen.

        Pauses Dashboard and Automatic Mode polling and presents ManualModeFrame.
        """
        if self._current_screen == "manual_mode":
            self.manual_mode_frame.on_show()
            return

        self.dashboard_frame.pause_polling()
        self.dashboard_frame.pack_forget()
        self.configuration_frame.pack_forget()
        self.automatic_mode_frame.pause_polling()
        self.automatic_mode_frame.pack_forget()

        self._current_screen = "manual_mode"
        self.manual_mode_frame.pack(fill="both", expand=True)
        self.manual_mode_frame.on_show()

    def show_automatic_mode(self) -> None:
        """
        Navigate to the Automatic Resource Simulation Mode screen.

        Pauses Dashboard and Manual Mode polling and presents AutomaticModeFrame.
        """
        if self._current_screen == "automatic_mode":
            self.automatic_mode_frame.on_show()
            return

        self.dashboard_frame.pause_polling()
        self.dashboard_frame.pack_forget()
        self.configuration_frame.pack_forget()
        self.manual_mode_frame.pause_polling()
        self.manual_mode_frame.pack_forget()

        self._current_screen = "automatic_mode"
        self.automatic_mode_frame.pack(fill="both", expand=True)
        self.automatic_mode_frame.on_show()

    def on_close(self) -> None:
        """Handle application exit, gracefully stopping the shared backend process."""
        logger.info("Application closing...")
        if self._owns_client and self.client.is_running():
            try:
                self.client.stop()
            except Exception as e:
                logger.error("Error stopping backend client: %s", e)
        if self._owns_root:
            self.root.destroy()

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()


def main() -> None:
    """Launch the main application controller."""
    app = BankerApp()
    app.run()


if __name__ == "__main__":
    main()
