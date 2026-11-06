"""
dashboard.py: Main Dashboard UI for Banker's Algorithm Simulator.

Provides DashboardFrame, integrating with BackendClient to display:
- Live backend connection status and bank state
- KPI Summary Cards (Customers, Resources, Available Pool, Safety Status)
- Dynamic Resource Availability & Pool Allocation bars
- Real-time Activity and Protocol Event stream
- Non-blocking message polling using Tkinter's after() loop
"""

from __future__ import annotations

import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

# Ensure frontend directory is importable
FRONTEND_DIR = Path(__file__).resolve().parent
if str(FRONTEND_DIR) not in sys.path:
    sys.path.insert(0, str(FRONTEND_DIR))

from api import BackendClient
from styles import (
    ACCENT_DANGER,
    ACCENT_DANGER_BG,
    ACCENT_INFO,
    ACCENT_PRIMARY,
    ACCENT_PRIMARY_BG,
    ACCENT_SUCCESS,
    ACCENT_SUCCESS_BG,
    ACCENT_WARNING,
    ACCENT_WARNING_BG,
    BG_CARD,
    BG_CARD_ALT,
    BG_CARD_HOVER,
    BG_MAIN,
    BG_SIDEBAR,
    BORDER_COLOR,
    BORDER_LIGHT,
    FONT_BODY,
    FONT_BODY_BOLD,
    FONT_CAPTION,
    FONT_CAPTION_BOLD,
    FONT_CARD_TITLE,
    FONT_MONO,
    FONT_MONO_BOLD,
    FONT_MONO_SM,
    FONT_SECTION,
    FONT_STAT_LARGE,
    FONT_STAT_MED,
    FONT_SUBTITLE,
    FONT_TITLE,
    LOG_COLORS,
    PAD_2XL,
    PAD_LG,
    PAD_MD,
    PAD_SM,
    PAD_XL,
    PAD_XS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    create_badge,
    create_card,
    setup_styles,
)

# Polling interval in milliseconds for non-blocking UI queue consumption
POLL_INTERVAL_MS = 40


class DashboardFrame(tk.Frame):
    """
    Main Dashboard Frame for the Banker's Algorithm Resource Management Simulator.

    Consumes data from BackendClient asynchronously and renders:
    1. Header with application title and backend connection status.
    2. Summary Cards: Customers, Resources, Available Pool, Safety Status.
    3. Resource Availability: Visual allocation bars and metrics per resource.
    4. Activity Stream: Chronological audit log of backend protocol events.
    """

    def __init__(
        self,
        master: tk.Widget,
        client: BackendClient,
        on_navigate_configuration: Optional[Callable[[], None]] = None,
        on_navigate_manual: Optional[Callable[[], None]] = None,
        on_navigate_automatic: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=BG_MAIN, **kwargs)
        self.client = client
        self.on_navigate_configuration = on_navigate_configuration
        self.on_navigate_manual = on_navigate_manual
        self.on_navigate_automatic = on_navigate_automatic

        # State tracking
        self._current_snapshot: Optional[Dict[str, Any]] = None
        self._is_initialized = False
        self._event_counter = 0
        self._polling_active = True

        # UI element references
        self._resource_widgets: List[tk.Widget] = []

        # Build UI layout
        self._build_header()
        self._build_summary_cards()
        self._build_lower_section()

        # Set initial uninitialized state display
        self._render_uninitialized_state()

        # Start non-blocking backend queue polling
        self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    # =========================================================================
    # UI Construction
    # =========================================================================

    def _build_header(self) -> None:
        """Build top navigation header with title and live status indicators."""
        header_frame = tk.Frame(self, bg=BG_MAIN)
        header_frame.pack(fill="x", padx=PAD_XL, pady=(PAD_XL, PAD_LG))

        # Left: Title and Subtitle
        title_box = tk.Frame(header_frame, bg=BG_MAIN)
        title_box.pack(side="left", fill="y")

        lbl_title = tk.Label(
            title_box,
            text="Banker's Algorithm Simulator",
            font=FONT_TITLE,
            bg=BG_MAIN,
            fg=TEXT_PRIMARY,
        )
        lbl_title.pack(anchor="w")

        lbl_subtitle = tk.Label(
            title_box,
            text="Deadlock Avoidance & Resource Management Dashboard",
            font=FONT_SUBTITLE,
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
        )
        lbl_subtitle.pack(anchor="w", pady=(2, 0))

        # Right: Connection Status & Action Buttons
        controls_box = tk.Frame(header_frame, bg=BG_MAIN)
        controls_box.pack(side="right", fill="y")

        # Connection badge
        self.badge_conn = tk.Label(
            controls_box,
            text="● Connecting...",
            font=FONT_CAPTION_BOLD,
            bg="#374151",
            fg="#E5E7EB",
            padx=PAD_MD,
            pady=4,
        )
        self.badge_conn.pack(side="left", padx=(0, PAD_SM))

        # State badge (Active / Uninitialized)
        self.badge_state = tk.Label(
            controls_box,
            text="Uninitialized",
            font=FONT_CAPTION_BOLD,
            bg=ACCENT_WARNING_BG,
            fg="#FDE047",
            padx=PAD_MD,
            pady=4,
        )
        self.badge_state.pack(side="left", padx=(0, PAD_MD))

        # Action Buttons
        btn_manual = ttk.Button(
            controls_box,
            text="Manual Mode",
            style="Secondary.TButton",
            command=self.navigate_to_manual,
        )
        btn_manual.pack(side="left", padx=(0, PAD_SM))

        btn_auto = ttk.Button(
            controls_box,
            text="Automatic Mode",
            style="Primary.TButton",
            command=self.navigate_to_automatic,
        )
        btn_auto.pack(side="left", padx=(0, PAD_SM))

        btn_config = ttk.Button(
            controls_box,
            text="Configure System",
            style="Secondary.TButton",
            command=self.navigate_to_configuration,
        )
        btn_config.pack(side="left", padx=(0, PAD_SM))

        btn_preset = ttk.Button(
            controls_box,
            text="Demo Preset",
            style="Secondary.TButton",
            command=self.load_demo_preset,
        )
        btn_preset.pack(side="left", padx=(0, PAD_SM))

        btn_safety = ttk.Button(
            controls_box,
            text="Safety Check",
            style="Secondary.TButton",
            command=self.request_safety_check,
        )
        btn_safety.pack(side="left", padx=(0, PAD_SM))

        btn_refresh = ttk.Button(
            controls_box,
            text="Refresh",
            style="Primary.TButton",
            command=self.refresh_snapshot,
        )
        btn_refresh.pack(side="left")

    def _build_summary_cards(self) -> None:
        """Build the four top KPI metric summary cards."""
        cards_container = tk.Frame(self, bg=BG_MAIN)
        cards_container.pack(fill="x", padx=PAD_XL, pady=(0, PAD_LG))

        # Configure 4 equal-width grid columns
        for c in range(4):
            cards_container.grid_columnconfigure(c, weight=1, uniform="summary_card")

        # Card 1: Total Customers
        self.card_customers = create_card(cards_container)
        self.card_customers.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_SM))
        self._build_card_content(
            self.card_customers,
            title="TOTAL CUSTOMERS",
            val_attr="lbl_cust_val",
            sub_attr="lbl_cust_sub",
            initial_val="—",
            initial_sub="Awaiting configuration",
        )

        # Card 2: Resource Types
        self.card_resources = create_card(cards_container)
        self.card_resources.grid(row=0, column=1, sticky="nsew", padx=PAD_SM)
        self._build_card_content(
            self.card_resources,
            title="RESOURCE TYPES",
            val_attr="lbl_res_val",
            sub_attr="lbl_res_sub",
            initial_val="—",
            initial_sub="Awaiting configuration",
        )

        # Card 3: Available Resources
        self.card_available = create_card(cards_container)
        self.card_available.grid(row=0, column=2, sticky="nsew", padx=PAD_SM)
        self._build_card_content(
            self.card_available,
            title="AVAILABLE POOL",
            val_attr="lbl_avail_val",
            sub_attr="lbl_avail_sub",
            initial_val="—",
            initial_sub="No active resource pool",
        )

        # Card 4: System Safety
        self.card_safety = create_card(cards_container)
        self.card_safety.grid(row=0, column=3, sticky="nsew", padx=(PAD_SM, 0))
        self._build_card_content(
            self.card_safety,
            title="SYSTEM SAFETY",
            val_attr="lbl_safety_val",
            sub_attr="lbl_safety_sub",
            initial_val="UNINITIALIZED",
            initial_sub="No snapshot loaded",
            val_color=TEXT_MUTED,
        )

    def _build_card_content(
        self,
        card: tk.Frame,
        title: str,
        val_attr: str,
        sub_attr: str,
        initial_val: str,
        initial_sub: str,
        val_color: str = TEXT_PRIMARY,
    ) -> None:
        """Helper to structure consistent summary card content."""
        lbl_title = tk.Label(
            card,
            text=title,
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
        )
        lbl_title.pack(anchor="w")

        lbl_val = tk.Label(
            card,
            text=initial_val,
            font=FONT_STAT_LARGE,
            bg=BG_CARD,
            fg=val_color,
        )
        lbl_val.pack(anchor="w", pady=(PAD_XS, PAD_XS))
        setattr(self, val_attr, lbl_val)

        lbl_sub = tk.Label(
            card,
            text=initial_sub,
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
            wraplength=200,
            justify="left",
        )
        lbl_sub.pack(anchor="w")
        setattr(self, sub_attr, lbl_sub)

    def _build_lower_section(self) -> None:
        """Build the split section: Resource Availability (Left) and Recent Activity (Right)."""
        lower_container = tk.Frame(self, bg=BG_MAIN)
        lower_container.pack(fill="both", expand=True, padx=PAD_XL, pady=(0, PAD_XL))

        lower_container.grid_columnconfigure(0, weight=5, uniform="lower_cols")
        lower_container.grid_columnconfigure(1, weight=6, uniform="lower_cols")
        lower_container.grid_rowconfigure(0, weight=1)

        # ---------------------------------------------------------------------
        # Left Column: Resource Availability & Utilization
        # ---------------------------------------------------------------------
        self.card_res_pool = create_card(lower_container)
        self.card_res_pool.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_SM))

        # Title row
        res_header = tk.Frame(self.card_res_pool, bg=BG_CARD)
        res_header.pack(fill="x", pady=(0, PAD_MD))

        lbl_res_section = tk.Label(
            res_header,
            text="Resource Availability & Pool Allocation",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_res_section.pack(side="left")

        # Scrollable container for dynamic resource bars
        self.res_content_frame = tk.Frame(self.card_res_pool, bg=BG_CARD)
        self.res_content_frame.pack(fill="both", expand=True)

        # ---------------------------------------------------------------------
        # Right Column: Recent Activity & Event Feed
        # ---------------------------------------------------------------------
        self.card_activity = create_card(lower_container)
        self.card_activity.grid(row=0, column=1, sticky="nsew", padx=(PAD_SM, 0))

        # Title and action toolbar
        act_header = tk.Frame(self.card_activity, bg=BG_CARD)
        act_header.pack(fill="x", pady=(0, PAD_MD))

        lbl_act_title = tk.Label(
            act_header,
            text="Live Activity & Protocol Events",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_act_title.pack(side="left")

        self.lbl_event_count = tk.Label(
            act_header,
            text="0 events",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self.lbl_event_count.pack(side="left", padx=PAD_MD)

        btn_clear = ttk.Button(
            act_header,
            text="Clear Feed",
            style="Secondary.TButton",
            command=self.clear_activity_log,
        )
        btn_clear.pack(side="right")

        # Styled dark event log text widget
        log_frame = tk.Frame(self.card_activity, bg=BG_SIDEBAR)
        log_frame.pack(fill="both", expand=True)

        self.txt_log = tk.Text(
            log_frame,
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            font=FONT_MONO,
            wrap="word",
            bd=0,
            padx=PAD_MD,
            pady=PAD_MD,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.txt_log.yview, style="Vertical.TScrollbar"
        )
        self.txt_log.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

        # Configure color tags for log message formatting
        self._configure_log_tags()

    def _configure_log_tags(self) -> None:
        """Set up text styling tags for the activity log."""
        self.txt_log.tag_configure("timestamp", foreground=TEXT_MUTED, font=FONT_MONO_SM)
        self.txt_log.tag_configure("text_normal", foreground=TEXT_PRIMARY, font=FONT_MONO)
        self.txt_log.tag_configure("text_muted", foreground=TEXT_SECONDARY, font=FONT_MONO)
        self.txt_log.tag_configure("accent", foreground=ACCENT_PRIMARY, font=FONT_MONO_BOLD)

        # Tag styles for each protocol badge
        for tag_name, (bg_color, fg_color) in LOG_COLORS.items():
            self.txt_log.tag_configure(
                f"badge_{tag_name}",
                background=bg_color,
                foreground=fg_color,
                font=FONT_MONO_BOLD,
                spacing1=2,
                spacing3=2,
            )

    # =========================================================================
    # Backend Queue Polling & Event Handling
    # =========================================================================

    def _poll_backend_queue(self) -> None:
        """
        Poll the BackendClient message queue from the Tkinter main thread.

        Reads all pending messages non-blockingly and schedules the next tick.
        """
        if not self.winfo_exists() or not getattr(self, "_polling_active", True):
            return

        # Update process connection indicator
        is_running = self.client.is_running()
        self._update_connection_indicator(is_running)

        # Process available messages (up to 50 per cycle to prevent starving UI)
        processed = 0
        while processed < 50:
            msg = self.client.get_message(timeout=0)
            if msg is None:
                break
            self._handle_backend_message(msg)
            processed += 1

        # Reschedule next poll
        if self.winfo_exists() and getattr(self, "_polling_active", True):
            self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    def pause_polling(self) -> None:
        """Pause queue polling when dashboard frame is hidden."""
        self._polling_active = False
        if hasattr(self, "_poll_job") and self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def resume_polling(self) -> None:
        """Resume polling and refresh snapshot from backend."""
        self.pause_polling()
        self._polling_active = True
        self.refresh_snapshot()
        if self.winfo_exists():
            self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    def on_show(self) -> None:
        """Called when Dashboard becomes visible. Refreshes snapshot from backend."""
        self.resume_polling()

    def destroy(self) -> None:
        """Cleanly cancel any pending after() timers upon destruction."""
        self.pause_polling()
        super().destroy()

    def _update_connection_indicator(self, is_running: bool) -> None:
        """Update connection badge in header based on process status."""
        if is_running:
            pid = self.client._process.pid if self.client._process else "?"
            self.badge_conn.configure(
                text=f"● Connected (PID: {pid})",
                bg=ACCENT_SUCCESS_BG,
                fg="#86EFAC",
            )
        else:
            self.badge_conn.configure(
                text="● Disconnected",
                bg=ACCENT_DANGER_BG,
                fg="#FCA5A5",
            )

    def _handle_backend_message(self, msg: Dict[str, Any]) -> None:
        """Dispatch backend response JSON to appropriate UI update handlers."""
        # Check for Snapshot response (contains customers, resources, available)
        if msg.get("status") == "ok" and "customers" in msg and "resources" in msg:
            self._apply_snapshot(msg)
            self._log_activity(
                "SNAPSHOT",
                f"State verified: Safe={msg.get('safe')} | "
                f"Available={msg.get('available')} | "
                f"Sequence={msg.get('safe_sequence')}",
            )
            return

        # Initialization ack
        if msg.get("status") == "ok" and msg.get("message") == "Bank initialized":
            self._is_initialized = True
            self.badge_state.configure(text="System Active", bg=ACCENT_SUCCESS_BG, fg="#86EFAC")
            self._log_activity("INIT", "Bank initialized with dynamic configuration.")
            return

        # Reset ack
        if msg.get("status") == "ok" and msg.get("message") == "Bank reset":
            self._render_uninitialized_state()
            self._log_activity("RESET", "Bank memory released; state reset to uninitialized.")
            return

        # Resource Request response
        status = msg.get("status")
        if status in ("granted", "unsafe", "exceeds_need", "unavailable", "invalid"):
            seq = msg.get("safe_sequence", [])
            tag = "GRANTED" if status == "granted" else "UNSAFE" if status == "unsafe" else "UNAVAIL"
            self._log_activity(
                tag,
                f"Request result: {status.upper()} | Safe sequence: {seq if seq else 'None'}",
            )
            return

        # Resource Release response
        if status in ("released", "invalid"):
            tag = "RELEASE" if status == "released" else "ERROR"
            self._log_activity(tag, f"Release operation: {status.upper()}")
            return

        # Automatic Simulation Events
        event = msg.get("event")
        if event == "customer_started":
            self._log_activity("AUTO", f"Customer {msg.get('customer')} thread spawned.")
            return
        if event == "request_result":
            res_code = msg.get("result")
            res_str = "GRANTED" if res_code == 1 else f"DENIED (code {res_code})"
            self._log_activity(
                "AUTO",
                f"Customer {msg.get('customer')} request evaluated: {res_str} | "
                f"Sequence: {msg.get('safe_sequence')}",
            )
            return
        if event == "customer_released":
            self._log_activity(
                "AUTO",
                f"Customer {msg.get('customer')} finished holding resources and released allocation.",
            )
            return
        if event == "automatic_complete":
            self._log_activity(
                "COMPLETE",
                f"Automatic simulation complete. {msg.get('threads_created')} customer threads joined.",
            )
            return
        if event == "process_terminated":
            self._log_activity(
                "ERROR",
                f"Backend process terminated unexpectedly (code: {msg.get('returncode')}).",
            )
            return

        # Error response
        if status == "error":
            err_msg = msg.get("message", "Unknown error")
            self._log_activity("ERROR", f"Backend error: {err_msg}")
            # If bank is not initialized, update state badge
            if "not initialized" in err_msg.lower():
                self._render_uninitialized_state()
            return

        # Generic fallback
        self._log_activity("INFO", str(msg))

    # =========================================================================
    # State & Snapshot Rendering
    # =========================================================================

    def _render_uninitialized_state(self) -> None:
        """Reset cards and availability section to clear uninitialized state."""
        self._is_initialized = False
        self._current_snapshot = None

        self.badge_state.configure(text="Uninitialized", bg=ACCENT_WARNING_BG, fg="#FDE047")

        # Summary cards
        self.lbl_cust_val.configure(text="—", fg=TEXT_MUTED)
        self.lbl_cust_sub.configure(text="Awaiting configuration")

        self.lbl_res_val.configure(text="—", fg=TEXT_MUTED)
        self.lbl_res_sub.configure(text="Awaiting configuration")

        self.lbl_avail_val.configure(text="—", fg=TEXT_MUTED)
        self.lbl_avail_sub.configure(text="No active resource pool")

        self.lbl_safety_val.configure(text="UNINITIALIZED", fg=TEXT_MUTED)
        self.lbl_safety_sub.configure(text="No snapshot loaded")

        # Clear resource pool container
        for w in self.res_content_frame.winfo_children():
            w.destroy()

        empty_box = tk.Frame(self.res_content_frame, bg=BG_CARD)
        empty_box.pack(expand=True, fill="both", pady=PAD_2XL)

        lbl_empty_icon = tk.Label(
            empty_box,
            text="📊",
            font=("Segoe UI", 24),
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_empty_icon.pack(pady=(0, PAD_SM))

        lbl_empty = tk.Label(
            empty_box,
            text="Backend is not initialized.",
            font=FONT_BODY_BOLD,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
        )
        lbl_empty.pack()

        lbl_empty_sub = tk.Label(
            empty_box,
            text="Load the 'Demo Preset' or initialize via configuration\nto inspect live resource pools and matrices.",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
            justify="center",
        )
        lbl_empty_sub.pack(pady=(PAD_XS, 0))

        btn_empty_config = ttk.Button(
            empty_box,
            text="Configure System →",
            style="Primary.TButton",
            command=self.navigate_to_configuration,
        )
        btn_empty_config.pack(pady=(PAD_MD, 0))

    def _apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Update KPI summary cards and dynamic resource bars from real snapshot data."""
        self._current_snapshot = snapshot
        self._is_initialized = True

        customers = snapshot.get("customers", 0)
        resources = snapshot.get("resources", 0)
        available = snapshot.get("available", [])
        allocation = snapshot.get("allocation", [])
        is_safe = snapshot.get("safe", False)
        safe_seq = snapshot.get("safe_sequence", [])

        # 1. Update State Badge
        self.badge_state.configure(text="System Active", bg=ACCENT_SUCCESS_BG, fg="#86EFAC")

        # 2. Update Customers Card
        self.lbl_cust_val.configure(text=str(customers), fg=TEXT_PRIMARY)
        self.lbl_cust_sub.configure(text=f"{customers} client processes managed")

        # 3. Update Resources Card
        self.lbl_res_val.configure(text=str(resources), fg=TEXT_PRIMARY)
        self.lbl_res_sub.configure(text=f"{resources} resource classes (R0–R{max(0, resources - 1)})")

        # 4. Update Available Resources Card
        avail_str = "[" + ", ".join(str(x) for x in available) + "]"
        self.lbl_avail_val.configure(text=avail_str, fg=TEXT_PRIMARY)
        self.lbl_avail_sub.configure(text="Free units ready for immediate allocation")

        # 5. Update Safety Status Card
        if is_safe:
            self.lbl_safety_val.configure(text="SAFE STATE", fg=ACCENT_SUCCESS)
            seq_display = " → ".join(f"P{i}" for i in safe_seq)
            self.lbl_safety_sub.configure(text=f"Safe Sequence:\n{seq_display}")
        else:
            self.lbl_safety_val.configure(text="UNSAFE STATE", fg=ACCENT_DANGER)
            self.lbl_safety_sub.configure(text="Deadlock risk! No safe sequence exists.")

        # 6. Render Resource Availability Bars
        self._render_resource_bars(resources, available, allocation)

    def _render_resource_bars(
        self,
        num_resources: int,
        available: List[int],
        allocation: List[List[int]],
    ) -> None:
        """Render modern horizontal allocation and availability bars for each resource."""
        for w in self.res_content_frame.winfo_children():
            w.destroy()

        # Calculate total and allocated for each resource j: Total[j] = Available[j] + Sum(Alloc[i][j])
        for j in range(num_resources):
            avail_j = available[j] if j < len(available) else 0
            alloc_j = sum(row[j] for row in allocation if j < len(row))
            total_j = avail_j + alloc_j
            pct_used = (alloc_j / total_j * 100) if total_j > 0 else 0

            # Color code based on utilization severity
            if pct_used >= 90:
                bar_color = ACCENT_DANGER
                badge_bg, badge_fg = ACCENT_DANGER_BG, "#FCA5A5"
            elif pct_used >= 70:
                bar_color = ACCENT_WARNING
                badge_bg, badge_fg = ACCENT_WARNING_BG, "#FDE047"
            else:
                bar_color = ACCENT_PRIMARY
                badge_bg, badge_fg = ACCENT_PRIMARY_BG, "#93C5FD"

            # Container row
            row_frame = tk.Frame(self.res_content_frame, bg=BG_CARD)
            row_frame.pack(fill="x", pady=PAD_SM)

            # Top label row: Resource name + Metrics
            top_line = tk.Frame(row_frame, bg=BG_CARD)
            top_line.pack(fill="x")

            lbl_name = tk.Label(
                top_line,
                text=f"Resource R{j}",
                font=FONT_BODY_BOLD,
                bg=BG_CARD,
                fg=TEXT_PRIMARY,
            )
            lbl_name.pack(side="left")

            lbl_metrics = tk.Label(
                top_line,
                text=f"Available: {avail_j}  /  Total: {total_j}  (Allocated: {alloc_j})",
                font=FONT_CAPTION,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
            )
            lbl_metrics.pack(side="right")

            # Progress Bar Canvas (12px height with smooth background and rounded ends)
            bar_canvas = tk.Canvas(
                row_frame,
                height=12,
                bg=BG_CARD,
                highlightthickness=0,
                bd=0,
            )
            bar_canvas.pack(fill="x", pady=(PAD_XS, 0))

            # Draw background trough and filled portion dynamically on configure
            def _draw_bar(
                event: tk.Event,
                canvas: tk.Canvas = bar_canvas,
                pct: float = pct_used,
                fill: str = bar_color,
            ) -> None:
                width = event.width
                canvas.delete("all")
                # Trough
                canvas.create_rectangle(0, 2, width, 10, fill=BORDER_COLOR, width=0)
                # Fill
                fill_w = max(0, min(width, int(width * (pct / 100.0))))
                if fill_w > 0:
                    canvas.create_rectangle(0, 2, fill_w, 10, fill=fill, width=0)

            bar_canvas.bind("<Configure>", _draw_bar)

    # =========================================================================
    # Activity Stream Logger
    # =========================================================================

    def _log_activity(self, tag: str, text: str) -> None:
        """
        Append a formatted, color-coded event message to the activity stream.

        Auto-scrolls to the newest message at the bottom.
        """
        now = datetime.now().strftime("%H:%M:%S")
        self._event_counter += 1
        self.lbl_event_count.configure(
            text=f"{self._event_counter} event{'s' if self._event_counter != 1 else ''}"
        )

        self.txt_log.configure(state="normal")

        # Timestamp
        self.txt_log.insert(tk.END, f"{now} ", "timestamp")

        # Colored Badge
        badge_tag = f"badge_{tag}" if f"badge_{tag}" in self.txt_log.tag_names() else "text_muted"
        self.txt_log.insert(tk.END, f" {tag} ", badge_tag)

        # Message text
        self.txt_log.insert(tk.END, f"  {text}\n", "text_normal")

        # Keep buffer capped to 400 lines
        lines = int(self.txt_log.index("end-1c").split(".")[0])
        if lines > 400:
            self.txt_log.delete("1.0", "50.0")

        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")

    def clear_activity_log(self) -> None:
        """Clear all messages from the activity log widget."""
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state="disabled")
        self._event_counter = 0
        self.lbl_event_count.configure(text="0 events")

    # =========================================================================
    # User Actions (Invoking real backend commands)
    # =========================================================================

    def refresh_snapshot(self) -> None:
        """Request a real snapshot from the backend via BackendClient.snapshot()."""
        if not self.client.is_running():
            self._log_activity("ERROR", "Cannot refresh: Backend process is not running.")
            return
        try:
            self.client.snapshot()
            self._log_activity("INFO", "Requested snapshot from backend.")
        except Exception as e:
            self._log_activity("ERROR", f"Failed to send snapshot command: {e}")

    def navigate_to_configuration(self) -> None:
        """Trigger navigation callback to switch to the Configuration screen."""
        if self.on_navigate_configuration:
            try:
                self.on_navigate_configuration()
            except Exception as e:
                self._log_activity("ERROR", f"Navigation callback error: {e}")
        else:
            self._log_activity("INFO", "Configure System requested (standalone mode).")

    def navigate_to_manual(self) -> None:
        """Trigger navigation callback to switch to Manual Mode screen."""
        if self.on_navigate_manual:
            try:
                self.on_navigate_manual()
            except Exception as e:
                self._log_activity("ERROR", f"Navigation callback error: {e}")
        else:
            self._log_activity("INFO", "Manual Mode requested (standalone mode).")

    def navigate_to_automatic(self) -> None:
        """Trigger navigation callback to switch to Automatic Mode screen."""
        if self.on_navigate_automatic:
            try:
                self.on_navigate_automatic()
            except Exception as e:
                self._log_activity("ERROR", f"Navigation callback error: {e}")
        else:
            self._log_activity("INFO", "Automatic Mode requested (standalone mode).")

    def request_safety_check(self) -> None:
        """Request a real safety check from the backend via BackendClient.safety_check()."""
        if not self.client.is_running():
            self._log_activity("ERROR", "Cannot run safety check: Backend is not running.")
            return
        try:
            self.client.safety_check()
            self._log_activity("INFO", "Requested safety check from backend.")
        except Exception as e:
            self._log_activity("ERROR", f"Failed to send safety check command: {e}")

    def load_demo_preset(self) -> None:
        """
        Initialize the backend with the classic 5-customer, 3-resource Banker's dataset.

        Total = [10, 5, 7]
        Safe sequence initially: P1 -> P3 -> P4 -> P0 -> P2.
        """
        if not self.client.is_running():
            self._log_activity("ERROR", "Cannot load demo preset: Backend is not running.")
            return

        customers = 5
        resources = 3
        total = [10, 5, 7]
        maximum = [
            [7, 5, 3],
            [3, 2, 2],
            [9, 0, 2],
            [2, 2, 2],
            [4, 3, 3],
        ]
        allocation = [
            [0, 1, 0],
            [2, 0, 0],
            [3, 0, 2],
            [2, 1, 1],
            [0, 0, 2],
        ]

        try:
            self.client.initialize(
                customers=customers,
                resources=resources,
                total=total,
                maximum=maximum,
                allocation=allocation,
            )
            self._log_activity(
                "INFO",
                f"Dispatched 'initialize' with 5 customers, 3 resources. Total: {total}",
            )
        except Exception as e:
            self._log_activity("ERROR", f"Failed to dispatch demo preset: {e}")


# =============================================================================
# Standalone Test Application Launcher
# =============================================================================
def main() -> None:
    """Launch the Dashboard directly as a standalone application for testing."""
    root = tk.Tk()
    root.title("Banker's Algorithm Resource Management Simulator")
    root.geometry("1100x720")
    root.minsize(960, 600)

    # Apply dark styles
    setup_styles(root)

    # Start BackendClient
    client = BackendClient()
    try:
        client.start()
        print(f"Backend started (PID: {client._process.pid if client._process else 'N/A'})")
    except Exception as e:
        print(f"Warning: Failed to start backend automatically: {e}")

    # Mount DashboardFrame
    dashboard = DashboardFrame(root, client=client)
    dashboard.pack(fill="both", expand=True)

    # Automatically query backend state
    root.after(200, dashboard.refresh_snapshot)

    # Clean shutdown on window close
    def on_closing() -> None:
        print("Closing application and terminating backend process...")
        if client.is_running():
            client.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

