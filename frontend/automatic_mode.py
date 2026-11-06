"""
automatic_mode.py: Phase 6 Automatic Simulation Mode for Banker's Algorithm Simulator.

Provides AutomaticModeFrame, enabling concurrent POSIX Pthreads simulation:
- Dynamically generates request vector inputs for each configured customer and resource.
- Quick presets: Fill Maximum Need, Fill Safe Baseline, Zero Out All, Randomize.
- Executes simulation using C backend's 'start_auto' command without simulating in Python.
- Real-time POSIX Pthreads Thread Monitor displaying reliable thread states:
  Waiting, Running, Granted, Rejected (Unsafe/Exceeds Need/Unavailable), Releasing, Completed.
- Live system state matrices and Available pool synchronization from backend snapshots.
- Non-blocking Tkinter event loop integration and shared BackendClient reuse.
- Seamless navigation between Dashboard, Manual Mode, and Automatic Mode.
"""

from __future__ import annotations

import logging
import random
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

logger = logging.getLogger("bankers.automatic_mode")

POLL_INTERVAL_MS = 40


class AutomaticModeFrame(tk.Frame):
    """
    Automatic Simulation Mode Frame.

    Coordinates concurrent customer threads in the C backend, receives streamed
    protocol events, monitors thread lifecycles, and visualizes system state changes.
    """

    def __init__(
        self,
        master: tk.Widget,
        client: BackendClient,
        on_navigate_dashboard: Optional[Callable[[], None]] = None,
        on_navigate_manual: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=BG_MAIN, **kwargs)
        self.client = client
        self.on_navigate_dashboard = on_navigate_dashboard
        self.on_navigate_manual = on_navigate_manual

        # State tracking
        self._current_snapshot: Optional[Dict[str, Any]] = None
        self._is_initialized = False
        self._is_simulating = False
        self._polling_active = True
        self._poll_job: Optional[str] = None
        self._event_counter = 0

        # Customer thread states: customer_id -> {"state": str, "detail": str, "variant": str}
        self._thread_states: Dict[int, Dict[str, Any]] = {}

        # Widget references
        self._req_entries: List[List[tk.Entry]] = []
        self._thread_cards: Dict[int, Dict[str, tk.Widget]] = {}
        self._matrix_labels: Dict[str, List[List[tk.Label]]] = {
            "allocation": [],
            "need": [],
        }

        # Build UI layout
        self._build_header()
        self._build_status_banner()
        self._build_overview_cards()
        self._build_main_content()

        # Render uninitialized placeholder initially
        self._render_uninitialized_state()

        # Start non-blocking backend queue polling
        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    # =========================================================================
    # UI Layout Construction
    # =========================================================================

    def _build_header(self) -> None:
        """Build screen header with title, status badges, and action buttons."""
        header_frame = tk.Frame(self, bg=BG_MAIN)
        header_frame.pack(fill="x", padx=PAD_XL, pady=(PAD_XL, PAD_MD))

        # Title & Subtitle
        title_box = tk.Frame(header_frame, bg=BG_MAIN)
        title_box.pack(side="left", fill="y")

        lbl_title = tk.Label(
            title_box,
            text="Automatic Resource Simulation",
            font=FONT_TITLE,
            bg=BG_MAIN,
            fg=TEXT_PRIMARY,
        )
        lbl_title.pack(anchor="w")

        lbl_subtitle = tk.Label(
            title_box,
            text="Concurrent POSIX Pthreads Banker's Algorithm Stress Testing",
            font=FONT_SUBTITLE,
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
        )
        lbl_subtitle.pack(anchor="w", pady=(2, 0))

        # Right Controls: Status Badges & Buttons
        controls_box = tk.Frame(header_frame, bg=BG_MAIN)
        controls_box.pack(side="right", fill="y")

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

        self.badge_state = tk.Label(
            controls_box,
            text="Uninitialized",
            font=FONT_CAPTION_BOLD,
            bg=ACCENT_WARNING_BG,
            fg="#FDE047",
            padx=PAD_MD,
            pady=4,
        )
        self.badge_state.pack(side="left", padx=(0, PAD_SM))

        self.badge_sim = tk.Label(
            controls_box,
            text="● Idle",
            font=FONT_CAPTION_BOLD,
            bg="#374151",
            fg="#E5E7EB",
            padx=PAD_MD,
            pady=4,
        )
        self.badge_sim.pack(side="left", padx=(0, PAD_MD))

        btn_refresh = ttk.Button(
            controls_box,
            text="Refresh State",
            style="Secondary.TButton",
            command=self.refresh_snapshot,
        )
        btn_refresh.pack(side="left", padx=(0, PAD_SM))

        if self.on_navigate_manual:
            btn_manual = ttk.Button(
                controls_box,
                text="Manual Mode",
                style="Secondary.TButton",
                command=self.navigate_to_manual,
            )
            btn_manual.pack(side="left", padx=(0, PAD_SM))

        btn_dashboard = ttk.Button(
            controls_box,
            text="← Dashboard",
            style="Primary.TButton",
            command=self.navigate_to_dashboard,
        )
        btn_dashboard.pack(side="left")

    def _build_status_banner(self) -> None:
        """Build notification banner displaying simulation status and feedback."""
        self.banner_frame = tk.Frame(
            self,
            bg=BG_CARD_ALT,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            padx=PAD_LG,
            pady=PAD_MD,
        )
        self.banner_frame.pack(fill="x", padx=PAD_XL, pady=(0, PAD_MD))

        top_line = tk.Frame(self.banner_frame, bg=BG_CARD_ALT)
        top_line.pack(fill="x")

        self.lbl_banner_title = tk.Label(
            top_line,
            text="Ready for Simulation",
            font=FONT_BODY_BOLD,
            bg=BG_CARD_ALT,
            fg=TEXT_SECONDARY,
        )
        self.lbl_banner_title.pack(side="left")

        self.lbl_banner_details = tk.Label(
            self.banner_frame,
            text="Configure request vectors for customer threads and click 'Start Simulation'.",
            font=FONT_CAPTION,
            bg=BG_CARD_ALT,
            fg=TEXT_MUTED,
            wraplength=950,
            justify="left",
        )
        self.lbl_banner_details.pack(anchor="w", pady=(PAD_XS, 0))

    def _build_overview_cards(self) -> None:
        """Build KPI overview metrics row: Dimensions, Available Pool, and System Safety."""
        overview_container = tk.Frame(self, bg=BG_MAIN)
        overview_container.pack(fill="x", padx=PAD_XL, pady=(0, PAD_MD))

        for c in range(3):
            overview_container.grid_columnconfigure(c, weight=1, uniform="ov_col")

        # Card 1: System Dimensions
        card_dim = create_card(overview_container)
        card_dim.grid(row=0, column=0, sticky="nsew", padx=(0, PAD_SM))

        tk.Label(
            card_dim, text="CONFIGURED DIMENSIONS", font=FONT_CARD_TITLE, bg=BG_CARD, fg=TEXT_MUTED
        ).pack(anchor="w")

        self.lbl_dim_val = tk.Label(
            card_dim, text="— Customers, — Resources", font=FONT_BODY_BOLD, bg=BG_CARD, fg=TEXT_PRIMARY
        )
        self.lbl_dim_val.pack(anchor="w", pady=(2, 0))

        # Card 2: Available Pool
        card_avail = create_card(overview_container)
        card_avail.grid(row=0, column=1, sticky="nsew", padx=PAD_SM)

        tk.Label(
            card_avail, text="AVAILABLE RESOURCE POOL", font=FONT_CARD_TITLE, bg=BG_CARD, fg=TEXT_MUTED
        ).pack(anchor="w")

        self.avail_chips_frame = tk.Frame(card_avail, bg=BG_CARD)
        self.avail_chips_frame.pack(anchor="w", pady=(2, 0))

        # Card 3: System Safety & Safe Sequence
        card_safety = create_card(overview_container)
        card_safety.grid(row=0, column=2, sticky="nsew", padx=(PAD_SM, 0))

        tk.Label(
            card_safety, text="SYSTEM SAFETY & SEQUENCE", font=FONT_CARD_TITLE, bg=BG_CARD, fg=TEXT_MUTED
        ).pack(anchor="w")

        safety_line = tk.Frame(card_safety, bg=BG_CARD)
        safety_line.pack(fill="x", pady=(2, 0))

        self.badge_safety_status = tk.Label(
            safety_line,
            text="● Unchecked",
            font=FONT_CAPTION_BOLD,
            bg=BORDER_COLOR,
            fg=TEXT_PRIMARY,
            padx=PAD_SM,
            pady=2,
        )
        self.badge_safety_status.pack(side="left", padx=(0, PAD_SM))

        self.lbl_safe_sequence = tk.Label(
            safety_line,
            text="—",
            font=FONT_MONO_BOLD,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
        )
        self.lbl_safe_sequence.pack(side="left")

    def _build_main_content(self) -> None:
        """Build two-column split layout: Left request config & Right thread monitor."""
        self.content_container = tk.Frame(self, bg=BG_MAIN)
        self.content_container.pack(fill="both", expand=True, padx=PAD_XL, pady=(0, PAD_XL))

        # Left Column: Customer Request Vectors Grid & Controls
        self.left_col = tk.Frame(self.content_container, bg=BG_MAIN, width=520)
        self.left_col.pack(side="left", fill="both", expand=False, padx=(0, PAD_MD))
        self.left_col.pack_propagate(False)

        # Right Column: Live Thread Activity Panel & Event Log
        self.right_col = tk.Frame(self.content_container, bg=BG_MAIN)
        self.right_col.pack(side="right", fill="both", expand=True)

        self._build_request_config_card(self.left_col)
        self._build_thread_monitor_card(self.right_col)
        self._build_activity_card(self.right_col)

    # -------------------------------------------------------------------------
    # Left Column: Request Configuration
    # -------------------------------------------------------------------------

    def _build_request_config_card(self, parent: tk.Widget) -> None:
        """Card holding dynamic request inputs for each customer and simulation execution buttons."""
        card = create_card(parent)
        card.pack(fill="both", expand=True)

        # Header & Quick Actions
        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            hdr,
            text="CUSTOMER REQUEST CONFIGURATION",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=ACCENT_PRIMARY,
        )
        lbl.pack(side="left")

        # Preset Buttons Row
        preset_row = tk.Frame(card, bg=BG_CARD)
        preset_row.pack(fill="x", pady=(0, PAD_SM))

        btn_fill_need = ttk.Button(
            preset_row,
            text="Fill Max Need",
            style="Secondary.TButton",
            command=self.fill_requests_with_need,
        )
        btn_fill_need.pack(side="left", padx=(0, PAD_XS))

        btn_fill_safe = ttk.Button(
            preset_row,
            text="Safe Baseline",
            style="Secondary.TButton",
            command=self.fill_requests_safe_baseline,
        )
        btn_fill_safe.pack(side="left", padx=(0, PAD_XS))

        btn_rand = ttk.Button(
            preset_row,
            text="Randomize",
            style="Secondary.TButton",
            command=self.randomize_requests,
        )
        btn_rand.pack(side="left", padx=(0, PAD_XS))

        btn_zero = ttk.Button(
            preset_row,
            text="Zero All",
            style="Secondary.TButton",
            command=self.clear_request_inputs,
        )
        btn_zero.pack(side="left")

        # Scrollable area for customer request rows
        canvas_box = tk.Frame(card, bg=BG_SIDEBAR)
        canvas_box.pack(fill="both", expand=True, pady=(PAD_XS, PAD_MD))

        self.req_canvas = tk.Canvas(canvas_box, bg=BG_SIDEBAR, bd=0, highlightthickness=0)
        v_scroll = ttk.Scrollbar(canvas_box, orient="vertical", command=self.req_canvas.yview)

        self.req_scroll_frame = tk.Frame(self.req_canvas, bg=BG_SIDEBAR)
        self.req_canvas.create_window((0, 0), window=self.req_scroll_frame, anchor="nw")
        self.req_canvas.configure(yscrollcommand=v_scroll.set)

        v_scroll.pack(side="right", fill="y")
        self.req_canvas.pack(side="left", fill="both", expand=True)

        self.req_scroll_frame.bind(
            "<Configure>",
            lambda e: self.req_canvas.configure(scrollregion=self.req_canvas.bbox("all")),
        )

        # Simulation Action Buttons Bar
        action_bar = tk.Frame(card, bg=BG_CARD)
        action_bar.pack(fill="x")

        self.btn_start = ttk.Button(
            action_bar,
            text="Start Simulation",
            style="Primary.TButton",
            command=self.start_simulation,
        )
        self.btn_start.pack(side="left", padx=(0, PAD_SM))

        self.btn_stop = ttk.Button(
            action_bar,
            text="Request Stop",
            style="Secondary.TButton",
            command=self.stop_simulation,
        )
        self.btn_stop.pack(side="left", padx=(0, PAD_MD))

        self.lbl_exec_hint = tk.Label(
            action_bar,
            text="Executes concurrently using POSIX Pthreads",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self.lbl_exec_hint.pack(side="left")

    # -------------------------------------------------------------------------
    # Right Column: Thread Monitor & Activity Stream
    # -------------------------------------------------------------------------

    def _build_thread_monitor_card(self, parent: tk.Widget) -> None:
        """Live POSIX Pthreads Thread Monitor displaying states for each customer thread."""
        card = create_card(parent)
        card.pack(fill="both", expand=True, pady=(0, PAD_SM))

        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            hdr,
            text="POSIX PTHREADS THREAD MONITOR",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=ACCENT_SUCCESS,
        )
        lbl.pack(side="left")

        lbl_hint = tk.Label(
            hdr,
            text="Real-time thread state stream from C backend",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_hint.pack(side="right")

        # Scrollable container for thread tiles
        canvas_box = tk.Frame(card, bg=BG_SIDEBAR)
        canvas_box.pack(fill="both", expand=True, pady=(PAD_XS, 0))

        self.threads_canvas = tk.Canvas(canvas_box, bg=BG_SIDEBAR, bd=0, highlightthickness=0)
        v_scroll = ttk.Scrollbar(canvas_box, orient="vertical", command=self.threads_canvas.yview)

        self.threads_content = tk.Frame(self.threads_canvas, bg=BG_SIDEBAR)
        self.threads_canvas.create_window((0, 0), window=self.threads_content, anchor="nw")
        self.threads_canvas.configure(yscrollcommand=v_scroll.set)

        v_scroll.pack(side="right", fill="y")
        self.threads_canvas.pack(side="left", fill="both", expand=True)

        self.threads_content.bind(
            "<Configure>",
            lambda e: self.threads_canvas.configure(scrollregion=self.threads_canvas.bbox("all")),
        )

    def _build_activity_card(self, parent: tk.Widget) -> None:
        """Card holding chronological protocol log stream."""
        card = create_card(parent)
        card.pack(fill="both", expand=True)

        hdr = tk.Frame(card, bg=BG_CARD)
        hdr.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            hdr,
            text="SIMULATION PROTOCOL LOG",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl.pack(side="left")

        self.lbl_event_count = tk.Label(
            hdr,
            text="0 events",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self.lbl_event_count.pack(side="right")

        log_frame = tk.Frame(card, bg=BG_SIDEBAR)
        log_frame.pack(fill="both", expand=True)

        self.txt_log = tk.Text(
            log_frame,
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            font=FONT_MONO,
            wrap="word",
            bd=0,
            padx=PAD_SM,
            pady=PAD_SM,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            height=6,
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.txt_log.yview, style="Vertical.TScrollbar"
        )
        self.txt_log.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

        # Tags
        self.txt_log.tag_configure("timestamp", foreground=TEXT_MUTED, font=FONT_MONO_SM)
        self.txt_log.tag_configure("text_normal", foreground=TEXT_PRIMARY, font=FONT_MONO)
        self.txt_log.tag_configure("text_muted", foreground=TEXT_SECONDARY, font=FONT_MONO)

        for tag_name, (bg_c, fg_c) in LOG_COLORS.items():
            self.txt_log.tag_configure(
                f"badge_{tag_name}",
                background=bg_c,
                foreground=fg_c,
                font=FONT_MONO_BOLD,
                spacing1=1,
                spacing3=1,
            )

    # =========================================================================
    # Dynamic Form Generation & Thread Monitor Initialization
    # =========================================================================

    def _render_request_grid(self, customers: int, resources: int) -> None:
        """Dynamically generate request input grid for N customers and M resources."""
        for w in self.req_scroll_frame.winfo_children():
            w.destroy()

        self._req_entries.clear()

        # Header Row
        hdr_row = tk.Frame(self.req_scroll_frame, bg=BG_SIDEBAR)
        hdr_row.pack(fill="x", padx=PAD_SM, pady=(PAD_SM, PAD_XS))

        lbl_corner = tk.Label(
            hdr_row, text="Customer", font=FONT_CAPTION_BOLD, bg=BG_SIDEBAR, fg=TEXT_MUTED, width=12, anchor="w"
        )
        lbl_corner.pack(side="left", padx=(0, PAD_SM))

        for j in range(resources):
            lbl_r = tk.Label(
                hdr_row,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_SIDEBAR,
                fg=ACCENT_PRIMARY,
                width=5,
            )
            lbl_r.pack(side="left", padx=2)

        # Rows for each customer
        for i in range(customers):
            row_frame = tk.Frame(self.req_scroll_frame, bg=BG_SIDEBAR)
            row_frame.pack(fill="x", padx=PAD_SM, pady=2)

            lbl_c = tk.Label(
                row_frame,
                text=f"Customer C{i}",
                font=FONT_BODY_BOLD,
                bg=BG_SIDEBAR,
                fg=TEXT_PRIMARY,
                width=12,
                anchor="w",
            )
            lbl_c.pack(side="left", padx=(0, PAD_SM))

            row_entries: List[tk.Entry] = []
            for j in range(resources):
                ent = tk.Entry(
                    row_frame,
                    width=5,
                    justify="center",
                    font=FONT_MONO_BOLD,
                    bg=BG_CARD,
                    fg=TEXT_PRIMARY,
                    insertbackground=TEXT_PRIMARY,
                    bd=0,
                    highlightthickness=1,
                    highlightbackground=BORDER_COLOR,
                )
                ent.insert(0, "0")
                ent.pack(side="left", padx=2)
                row_entries.append(ent)

            self._req_entries.append(row_entries)

    def _render_thread_cards(self, customers: int) -> None:
        """Render thread monitoring tiles for N customer threads."""
        for w in self.threads_content.winfo_children():
            w.destroy()

        self._thread_cards.clear()
        self._thread_states.clear()

        for i in range(customers):
            self._thread_states[i] = {
                "state": "WAITING",
                "detail": "Ready to launch",
                "variant": "muted",
            }

            tile = tk.Frame(
                self.threads_content,
                bg=BG_CARD,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                padx=PAD_SM,
                pady=PAD_XS,
            )
            tile.pack(fill="x", padx=PAD_SM, pady=2)

            # Left: Customer Label
            lbl_id = tk.Label(
                tile,
                text=f"Thread P{i} (Customer C{i})",
                font=FONT_BODY_BOLD,
                bg=BG_CARD,
                fg=TEXT_PRIMARY,
                width=20,
                anchor="w",
            )
            lbl_id.pack(side="left")

            # Center: State Badge
            badge = tk.Label(
                tile,
                text="WAITING",
                font=FONT_CAPTION_BOLD,
                bg="#374151",
                fg="#E5E7EB",
                padx=PAD_SM,
                pady=2,
                width=16,
            )
            badge.pack(side="left", padx=PAD_SM)

            # Right: Detail description
            lbl_desc = tk.Label(
                tile,
                text="Ready to launch",
                font=FONT_CAPTION,
                bg=BG_CARD,
                fg=TEXT_MUTED,
                anchor="w",
            )
            lbl_desc.pack(side="left", fill="x", expand=True)

            self._thread_cards[i] = {
                "tile": tile,
                "badge": badge,
                "detail": lbl_desc,
            }

    def _update_thread_tile(self, customer_id: int, state: str, detail: str, variant: str) -> None:
        """Update visual state and badge for a specific customer thread tile."""
        self._thread_states[customer_id] = {
            "state": state,
            "detail": detail,
            "variant": variant,
        }

        if customer_id not in self._thread_cards:
            return

        card = self._thread_cards[customer_id]
        badge = card["badge"]
        lbl_detail = card["detail"]

        styles = {
            "waiting": ("#374151", "#E5E7EB"),
            "running": (ACCENT_PRIMARY_BG, "#93C5FD"),
            "granted": (ACCENT_SUCCESS_BG, "#86EFAC"),
            "rejected_unsafe": (ACCENT_WARNING_BG, "#FDE047"),
            "rejected_need": (ACCENT_DANGER_BG, "#FCA5A5"),
            "rejected_unavail": (ACCENT_WARNING_BG, "#FDE047"),
            "rejected_invalid": (ACCENT_DANGER_BG, "#FCA5A5"),
            "completed": (ACCENT_SUCCESS_BG, "#86EFAC"),
            "muted": ("#374151", "#9CA3AF"),
        }
        bg_col, fg_col = styles.get(variant, ("#374151", "#E5E7EB"))

        badge.configure(text=state, bg=bg_col, fg=fg_col)
        lbl_detail.configure(text=detail, fg=fg_col if variant != "muted" else TEXT_MUTED)

    # =========================================================================
    # Preset Handlers
    # =========================================================================

    def fill_requests_with_need(self) -> None:
        """Fill all request inputs with the customer's exact remaining Need vector."""
        if not self._current_snapshot:
            return
        need = self._current_snapshot.get("need", [])
        for i, row in enumerate(self._req_entries):
            c_need = need[i] if i < len(need) else []
            for j, ent in enumerate(row):
                val = c_need[j] if j < len(c_need) else 0
                ent.delete(0, tk.END)
                ent.insert(0, str(val))

    def fill_requests_safe_baseline(self) -> None:
        """Fill inputs with modest requests (min(1, need) for each resource)."""
        if not self._current_snapshot:
            return
        need = self._current_snapshot.get("need", [])
        for i, row in enumerate(self._req_entries):
            c_need = need[i] if i < len(need) else []
            for j, ent in enumerate(row):
                val = 1 if (j < len(c_need) and c_need[j] > 0) else 0
                ent.delete(0, tk.END)
                ent.insert(0, str(val))

    def randomize_requests(self) -> None:
        """Fill inputs with random valid quantities up to current customer Need."""
        if not self._current_snapshot:
            return
        need = self._current_snapshot.get("need", [])
        for i, row in enumerate(self._req_entries):
            c_need = need[i] if i < len(need) else []
            for j, ent in enumerate(row):
                max_val = c_need[j] if j < len(c_need) else 0
                val = random.randint(0, max_val) if max_val > 0 else 0
                ent.delete(0, tk.END)
                ent.insert(0, str(val))

    def clear_request_inputs(self) -> None:
        """Reset all request entries to 0."""
        for row in self._req_entries:
            for ent in row:
                ent.delete(0, tk.END)
                ent.insert(0, "0")

    # =========================================================================
    # Simulation Execution Actions
    # =========================================================================

    def start_simulation(self) -> None:
        """
        Validate request grid and dispatch 'start_auto' to the C backend.

        Guards against duplicate executions while simulation is running.
        """
        if self._is_simulating:
            logger.warning("Simulation already running.")
            return

        if not self._is_initialized or not self._current_snapshot:
            self.set_status("Cannot start: Bank is not initialized.", variant="danger")
            return

        if not self.client.is_running():
            self.set_status("Cannot start: Backend process is not running.", variant="danger")
            return

        customers = self._current_snapshot.get("customers", len(self._req_entries))
        resources = self._current_snapshot.get("resources", 0)

        requests: List[List[int]] = []
        for i, row in enumerate(self._req_entries):
            req_row: List[int] = []
            for j, ent in enumerate(row):
                raw = ent.get().strip()
                if not raw:
                    raw = "0"
                try:
                    v = int(raw)
                    if v < 0:
                        raise ValueError()
                    req_row.append(v)
                except ValueError:
                    self.set_status(
                        f"Validation Error: All requests must be nonnegative integers (Customer C{i}, R{j}).",
                        variant="danger",
                    )
                    return
            requests.append(req_row)

        if len(requests) != customers:
            self.set_status(f"Request grid size ({len(requests)}) does not match customer count ({customers}).", variant="danger")
            return

        # Lock UI
        self._is_simulating = True
        self.btn_start.configure(state="disabled", text="Simulating...")
        self.badge_sim.configure(text="● Running...", bg=ACCENT_PRIMARY_BG, fg="#93C5FD")

        # Reset all thread tiles to WAITING
        for i in range(customers):
            self._update_thread_tile(i, "WAITING", f"Request: {requests[i]}", "waiting")

        self.set_status(
            f"Simulation Started: Dispatching {customers} concurrent customer threads to C backend...",
            variant="info",
            details="Customer threads will concurrently submit requests, hold granted resources, and release.",
        )
        self._log_activity("AUTO", f"Dispatched 'start_auto' with {customers} request vectors.")

        try:
            self.client.start_auto(requests)
        except Exception as e:
            self._is_simulating = False
            self.btn_start.configure(state="normal", text="Start Simulation")
            self.badge_sim.configure(text="● Error", bg=ACCENT_DANGER_BG, fg="#FCA5A5")
            self.set_status(f"Failed to start simulation: {e}", variant="danger")

    def stop_simulation(self) -> None:
        """
        Handle Request Stop.

        The C backend executes customer thread cycles atomically (each thread holds
        allocated resources for 500ms before releasing and joining).
        Terminating the backend process mid-simulation would cause resource leaks or
        corrupt IPC state. This method requests stop gracefully, informing the user
        that active threads will complete their current 500ms cycle before simulation terminates.
        """
        if not self._is_simulating:
            self.set_status("No simulation is currently running.", variant="info")
            return

        self.set_status(
            "Stop Requested: Active customer threads are completing their atomic 500ms cycle. Simulation will join shortly.",
            variant="warning",
            details="Backend customer threads complete their atomic cycle safely before joining; the backend process remains intact.",
        )
        self._log_activity("INFO", "Stop requested: Active customer threads completing atomic cycle before join.")

    # =========================================================================
    # Backend Queue Polling & Event Handling
    # =========================================================================

    def _poll_backend_queue(self) -> None:
        """Non-blocking queue polling loop running on the Tkinter main thread."""
        if not self.winfo_exists() or not getattr(self, "_polling_active", True):
            return

        is_running = self.client.is_running()
        self._update_connection_indicator(is_running)

        processed = 0
        while processed < 50:
            msg = self.client.get_message(timeout=0)
            if msg is None:
                break
            self._handle_backend_message(msg)
            processed += 1

        if self.winfo_exists() and getattr(self, "_polling_active", True):
            self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    def _handle_backend_message(self, msg: Dict[str, Any]) -> None:
        """Dispatch backend response JSON to event and thread monitor handlers."""
        event_name = msg.get("event")
        status = msg.get("status")

        # 1. Customer thread spawned
        if event_name == "customer_started":
            c = msg.get("customer", 0)
            self._update_thread_tile(c, "RUNNING", "Thread active, requesting allocation...", "running")
            self._log_activity("START", f"Customer C{c} thread active.")
            return

        # 2. Resource request result
        if event_name == "request_result":
            c = msg.get("customer", 0)
            res = msg.get("result", 0)
            seq = msg.get("safe_sequence", [])
            seq_str = " → ".join(f"C{x}" for x in seq) if seq else "None"

            if res == 1:  # BANK_GRANTED
                self._update_thread_tile(
                    c, "GRANTED", f"Granted! Holding resources (Safe: {seq_str})", "granted"
                )
                self._log_activity("GRANTED", f"Customer C{c} request granted. Safe: {seq_str}")
            elif res == 0:  # BANK_UNSAFE
                self._update_thread_tile(
                    c, "REJECTED", "Denied: Unsafe state (deadlock risk). Rolled back.", "rejected_unsafe"
                )
                self._log_activity("UNSAFE", f"Customer C{c} request denied (unsafe state). Rolled back.")
            elif res == -1:  # BANK_EXCEEDS_NEED
                self._update_thread_tile(
                    c, "REJECTED", "Denied: Exceeds declared maximum need.", "rejected_need"
                )
                self._log_activity("EXCEEDS", f"Customer C{c} request exceeds declared need.")
            elif res == -2:  # BANK_UNAVAILABLE
                self._update_thread_tile(
                    c, "REJECTED", "Denied: Resources unavailable in pool.", "rejected_unavail"
                )
                self._log_activity("UNAVAIL", f"Customer C{c} request exceeds available pool.")
            else:
                self._update_thread_tile(
                    c, "REJECTED", "Denied: Invalid parameters.", "rejected_invalid"
                )
                self._log_activity("ERROR", f"Customer C{c} request rejected as invalid.")
            return

        # 3. Customer released resources
        if event_name == "customer_released":
            c = msg.get("customer", 0)
            self._update_thread_tile(c, "COMPLETED", "Resources released back to pool. Finished.", "completed")
            self._log_activity("RELEASE", f"Customer C{c} released allocated resources.")
            return

        # 3b. Customer release failed
        if event_name == "release_failed":
            c = msg.get("customer", 0)
            err = msg.get("message", "Release failed")
            self._update_thread_tile(c, "RELEASE FAILED", f"Failed to release resources: {err}", "rejected_need")
            self._log_activity("ERROR", f"Customer C{c} release failed: {err}")
            return

        # 4. Automatic simulation complete
        if event_name == "automatic_complete":
            threads_created = msg.get("threads_created", 0)
            threads_expected = msg.get("threads_expected", threads_created)
            self._is_simulating = False
            self.btn_start.configure(state="normal", text="Start Simulation")

            # Check if there was partial creation failure
            if threads_created < threads_expected:
                self.badge_sim.configure(text="● Partial Failure", bg=ACCENT_WARNING_BG, fg="#FDE68A")
                for c in range(threads_created, threads_expected):
                    self._update_thread_tile(c, "NOT CREATED", "Thread creation failed in C backend.", "rejected_need")
                self.set_status(
                    f"SIMULATION PARTIAL: Only {threads_created}/{threads_expected} customer threads were created.",
                    variant="warning",
                    details=f"The backend could not create all threads ({threads_created} of {threads_expected} spawned). Created threads joined safely.",
                )
                self._log_activity("WARNING", f"Simulation finished with partial threads: {threads_created}/{threads_expected} created.")
            else:
                self.badge_sim.configure(text="● Completed", bg=ACCENT_SUCCESS_BG, fg="#86EFAC")
                self.set_status(
                    f"SIMULATION COMPLETE: {threads_created} customer threads joined successfully.",
                    variant="success",
                    details="All thread requests and releases processed. Final bank state synchronized.",
                )
                self._log_activity("COMPLETE", f"Automatic simulation complete. {threads_created} threads joined.")

            # DO NOT mark WAITING or RUNNING customers as COMPLETED!
            # Instead, update any threads that never finished cleanly to reflect accurate terminal state
            for c, state_info in self._thread_states.items():
                st = state_info.get("state")
                if st == "RUNNING":
                    self._update_thread_tile(c, "STOPPED", "Thread joined without releasing.", "rejected_invalid")
                elif st == "WAITING":
                    if c >= threads_created:
                        self._update_thread_tile(c, "NOT CREATED", "Thread creation failed.", "rejected_need")
                    else:
                        self._update_thread_tile(c, "INCOMPLETE", "Thread joined before execution.", "rejected_invalid")
            return

        # 5. Snapshot response
        if status == "ok" and "customers" in msg and "resources" in msg and "available" in msg:
            self._apply_snapshot(msg)
            return

        # 6. Backend error
        if status == "error":
            err_msg = msg.get("message", "Unknown backend error")
            self._is_simulating = False
            self.btn_start.configure(state="normal", text="Start Simulation")
            self.badge_sim.configure(text="● Error", bg=ACCENT_DANGER_BG, fg="#FCA5A5")

            if "not initialized" in err_msg.lower():
                self._render_uninitialized_state()
                self.set_status("Bank is not initialized. Please configure the system first.", variant="warning")
            else:
                self.set_status(f"Backend Error: {err_msg}", variant="danger")
            self._log_activity("ERROR", f"Backend error: {err_msg}")

    # =========================================================================
    # Snapshot Application
    # =========================================================================

    def _apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Apply live snapshot from backend to overview indicators and tables."""
        self._current_snapshot = snapshot
        self._is_initialized = True

        customers = snapshot.get("customers", 0)
        resources = snapshot.get("resources", 0)
        available = snapshot.get("available", [])
        is_safe = snapshot.get("safe", False)
        safe_seq = snapshot.get("safe_sequence", [])

        # Update Dimensions Card
        self.lbl_dim_val.configure(
            text=f"{customers} Customers, {resources} Resource Types"
        )

        # Update Header State Badge
        if is_safe:
            self.badge_state.configure(text="System Active (Safe)", bg=ACCENT_SUCCESS_BG, fg="#86EFAC")
            self.badge_safety_status.configure(text="● SAFE STATE", bg=ACCENT_SUCCESS_BG, fg="#86EFAC")
            seq_display = " → ".join(f"C{x}" for x in safe_seq) if safe_seq else "Empty"
            self.lbl_safe_sequence.configure(text=seq_display, fg="#86EFAC")
        else:
            self.badge_state.configure(text="System Active (Unsafe)", bg=ACCENT_DANGER_BG, fg="#FCA5A5")
            self.badge_safety_status.configure(text="● UNSAFE STATE", bg=ACCENT_DANGER_BG, fg="#FCA5A5")
            self.lbl_safe_sequence.configure(text="None (Deadlock Risk)", fg="#FCA5A5")

        # Update Available Pool chips
        for w in self.avail_chips_frame.winfo_children():
            w.destroy()

        for j in range(resources):
            val = available[j] if j < len(available) else 0
            chip = tk.Frame(
                self.avail_chips_frame,
                bg=BG_SIDEBAR,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                padx=PAD_SM,
                pady=2,
            )
            chip.pack(side="left", padx=(0, PAD_XS))

            tk.Label(chip, text=f"R{j}: ", font=FONT_CAPTION_BOLD, bg=BG_SIDEBAR, fg=ACCENT_PRIMARY).pack(side="left")
            tk.Label(chip, text=str(val), font=FONT_MONO_BOLD, bg=BG_SIDEBAR, fg=TEXT_PRIMARY).pack(side="left")

        # Generate Request grid if dimensions mismatch
        if len(self._req_entries) != customers or (self._req_entries and len(self._req_entries[0]) != resources):
            self._render_request_grid(customers, resources)

        # Generate Thread monitor tiles if customer count changed
        if len(self._thread_cards) != customers:
            self._render_thread_cards(customers)

        if not self._is_simulating:
            self._log_activity(
                "SNAPSHOT",
                f"State verified: Safe={is_safe} | Available={available} | Sequence={safe_seq}",
            )

    def _render_uninitialized_state(self) -> None:
        """Render UI when bank backend is not yet initialized."""
        self._is_initialized = False
        self._current_snapshot = None
        self._is_simulating = False

        self.badge_state.configure(text="Uninitialized", bg=ACCENT_WARNING_BG, fg="#FDE047")
        self.badge_sim.configure(text="● Idle", bg="#374151", fg="#E5E7EB")
        self.badge_safety_status.configure(text="● Uninitialized", bg=BORDER_COLOR, fg=TEXT_MUTED)
        self.lbl_safe_sequence.configure(text="—", fg=TEXT_MUTED)
        self.lbl_dim_val.configure(text="— Customers, — Resources")

        for w in self.avail_chips_frame.winfo_children():
            w.destroy()
        tk.Label(
            self.avail_chips_frame,
            text="No active resource pool. Bank must be initialized.",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        ).pack(side="left")

        for w in self.req_scroll_frame.winfo_children():
            w.destroy()
        tk.Label(
            self.req_scroll_frame,
            text="Customer request configuration will appear once bank is initialized.",
            font=FONT_BODY,
            bg=BG_SIDEBAR,
            fg=TEXT_MUTED,
            pady=PAD_2XL,
        ).pack(anchor="center")

        for w in self.threads_content.winfo_children():
            w.destroy()
        tk.Label(
            self.threads_content,
            text="Thread monitor tiles will appear once bank is initialized.",
            font=FONT_BODY,
            bg=BG_SIDEBAR,
            fg=TEXT_MUTED,
            pady=PAD_2XL,
        ).pack(anchor="center")

    # =========================================================================
    # Activity Stream & Banner Utilities
    # =========================================================================

    def _log_activity(self, tag: str, text: str) -> None:
        """Append an event to the chronological activity log."""
        if not hasattr(self, "txt_log") or not self.txt_log.winfo_exists():
            return

        now = datetime.now().strftime("%H:%M:%S")
        self._event_counter += 1
        self.lbl_event_count.configure(
            text=f"{self._event_counter} event{'s' if self._event_counter != 1 else ''}"
        )

        self.txt_log.configure(state="normal")
        self.txt_log.insert(tk.END, f"{now} ", "timestamp")

        badge_tag = f"badge_{tag}" if f"badge_{tag}" in self.txt_log.tag_names() else "text_muted"
        self.txt_log.insert(tk.END, f" {tag} ", badge_tag)
        self.txt_log.insert(tk.END, f"  {text}\n", "text_normal")

        lines = int(self.txt_log.index("end-1c").split(".")[0])
        if lines > 300:
            self.txt_log.delete("1.0", "40.0")

        self.txt_log.see(tk.END)
        self.txt_log.configure(state="disabled")

    def set_status(
        self,
        title: str,
        variant: str = "info",
        details: Optional[str] = None,
    ) -> None:
        """Update top status banner styling and text."""
        if not hasattr(self, "lbl_banner_title") or not self.lbl_banner_title.winfo_exists():
            return

        variant_styles = {
            "success": (ACCENT_SUCCESS_BG, "#86EFAC", ACCENT_SUCCESS),
            "danger": (ACCENT_DANGER_BG, "#FCA5A5", ACCENT_DANGER),
            "warning": (ACCENT_WARNING_BG, "#FDE047", ACCENT_WARNING),
            "info": (ACCENT_PRIMARY_BG, "#93C5FD", ACCENT_PRIMARY),
        }
        bg_col, fg_col, border_col = variant_styles.get(variant, (BG_CARD_ALT, TEXT_PRIMARY, BORDER_COLOR))

        self.banner_frame.configure(bg=bg_col, highlightbackground=border_col)
        self.banner_frame.winfo_children()[0].configure(bg=bg_col)
        self.lbl_banner_title.configure(text=title, bg=bg_col, fg=fg_col)

        if details:
            self.lbl_banner_details.configure(text=details, bg=bg_col, fg=fg_col)
            self.lbl_banner_details.pack(anchor="w", pady=(PAD_XS, 0))
        else:
            self.lbl_banner_details.pack_forget()

    def _update_connection_indicator(self, is_running: bool) -> None:
        """Update process connection badge in header."""
        if is_running:
            pid = getattr(self.client._process, "pid", "?") if self.client._process else "?"
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

    # =========================================================================
    # Navigation & Lifecycle
    # =========================================================================

    def refresh_snapshot(self) -> None:
        """Request live snapshot from C backend."""
        if not self.client.is_running():
            self.set_status("Cannot refresh: Backend is not running.", variant="danger")
            return
        try:
            self.client.snapshot()
        except Exception as e:
            self.set_status(f"Failed to request snapshot: {e}", variant="danger")

    def navigate_to_dashboard(self) -> None:
        """Trigger navigation callback to return to Dashboard."""
        if self.on_navigate_dashboard:
            try:
                self.on_navigate_dashboard()
            except Exception as e:
                logger.error("Navigation error: %s", e)
        else:
            self._log_activity("INFO", "Dashboard navigation triggered (standalone mode).")

    def navigate_to_manual(self) -> None:
        """Trigger navigation callback to switch to Manual Mode."""
        if self.on_navigate_manual:
            try:
                self.on_navigate_manual()
            except Exception as e:
                logger.error("Navigation error: %s", e)
        else:
            self._log_activity("INFO", "Manual Mode navigation triggered (standalone mode).")

    def pause_polling(self) -> None:
        """Pause queue polling when Automatic Mode frame is hidden."""
        self._polling_active = False
        if self._poll_job:
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
        """Called when Automatic Mode screen becomes visible."""
        self.resume_polling()

    def destroy(self) -> None:
        """Clean up pending callbacks upon destruction."""
        self.pause_polling()
        super().destroy()


# =============================================================================
# Standalone Testing Launcher
# =============================================================================
def main() -> None:
    """Launch AutomaticMode directly for interactive testing."""
    root = tk.Tk()
    root.title("Banker's Algorithm Simulator — Automatic Mode")
    root.geometry("1100x750")
    root.minsize(960, 620)
    setup_styles(root)

    client = BackendClient()
    try:
        client.start()
    except Exception as e:
        print("Backend startup failed:", e)

    frame = AutomaticModeFrame(root, client=client)
    frame.pack(fill="both", expand=True)

    root.after(200, frame.refresh_snapshot)

    def on_closing() -> None:
        if client.is_running():
            client.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

