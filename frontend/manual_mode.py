"""
manual_mode.py: Phase 5 Manual Resource Management Mode for Banker's Algorithm Simulator.

Provides ManualModeFrame, allowing interactive customer resource requests and releases
with real-time Banker's Algorithm validation strictly powered by the C backend.

Key Features:
- Dynamic Customer Selector populated from live C backend snapshot.
- Detailed metrics per customer: Maximum Claim, Current Allocation, Remaining Need.
- Dynamic Resource Request form with instant Banker's validation:
  Handles GRANTED, EXCEEDS NEED, RESOURCES UNAVAILABLE, UNSAFE STATE, and INVALID.
- Dynamic Resource Release form with client-side & backend limit validation.
- Live State Display: Available vector, Allocation, Maximum, and Need matrices
  with row-highlighting for the active customer.
- Activity feed logging requests, outcomes, releases, and safety transitions.
- Seamless navigation back to Dashboard while sharing a single BackendClient.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger("bankers.manual_mode")

POLL_INTERVAL_MS = 40


class ManualModeFrame(tk.Frame):
    """
    Manual Resource Management Mode UI Frame.

    Enables interactive, step-by-step evaluation of the Banker's Algorithm.
    Users select a customer, enter resource request or release vectors,
    and submit them to the C backend. The backend evaluates safety, updates
    or rolls back tentative allocations, and returns live status and snapshots.
    """

    def __init__(
        self,
        master: tk.Widget,
        client: BackendClient,
        on_navigate_dashboard: Optional[Callable[[], None]] = None,
        on_navigate_automatic: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=BG_MAIN, **kwargs)
        self.client = client
        self.on_navigate_dashboard = on_navigate_dashboard
        self.on_navigate_automatic = on_navigate_automatic

        # State tracking
        self._current_snapshot: Optional[Dict[str, Any]] = None
        self._is_initialized = False
        self._selected_customer_idx = 0
        self._polling_active = True
        self._poll_job: Optional[str] = None
        self._event_counter = 0

        # Pending operation tracking ("request", "release", "refresh")
        self._pending_op: Optional[str] = None
        self._pending_customer: Optional[int] = None
        self._pending_vector: Optional[List[int]] = None

        # Widget references
        self.req_entries: List[tk.Entry] = []
        self.rel_entries: List[tk.Entry] = []
        self._matrix_labels: Dict[str, List[List[tk.Label]]] = {
            "allocation": [],
            "maximum": [],
            "need": [],
        }

        # Build UI layout
        self._build_header()
        self._build_status_banner()
        self._build_main_layout()

        # Render uninitialized placeholder initially
        self._render_uninitialized_state()

        # Start non-blocking backend queue polling
        self._poll_job = self.after(POLL_INTERVAL_MS, self._poll_backend_queue)

    # =========================================================================
    # UI Layout Construction
    # =========================================================================

    def _build_header(self) -> None:
        """Build top navigation header with title and action buttons."""
        header_frame = tk.Frame(self, bg=BG_MAIN)
        header_frame.pack(fill="x", padx=PAD_XL, pady=(PAD_XL, PAD_MD))

        # Left: Title & Subtitle
        title_box = tk.Frame(header_frame, bg=BG_MAIN)
        title_box.pack(side="left", fill="y")

        lbl_title = tk.Label(
            title_box,
            text="Manual Resource Management",
            font=FONT_TITLE,
            bg=BG_MAIN,
            fg=TEXT_PRIMARY,
        )
        lbl_title.pack(anchor="w")

        lbl_subtitle = tk.Label(
            title_box,
            text="Interactive Banker's Algorithm Allocation & Safety Verification",
            font=FONT_SUBTITLE,
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
        )
        lbl_subtitle.pack(anchor="w", pady=(2, 0))

        # Right: Connection Badge, Safety Badge, & Navigation Buttons
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
        self.badge_state.pack(side="left", padx=(0, PAD_MD))

        btn_refresh = ttk.Button(
            controls_box,
            text="Refresh State",
            style="Secondary.TButton",
            command=self.refresh_snapshot,
        )
        btn_refresh.pack(side="left", padx=(0, PAD_SM))

        btn_auto = ttk.Button(
            controls_box,
            text="Automatic Mode",
            style="Secondary.TButton",
            command=self.navigate_to_automatic,
        )
        btn_auto.pack(side="left", padx=(0, PAD_SM))

        btn_dashboard = ttk.Button(
            controls_box,
            text="← Dashboard",
            style="Primary.TButton",
            command=self.navigate_to_dashboard,
        )
        btn_dashboard.pack(side="left")

    def _build_status_banner(self) -> None:
        """Build top notification/outcome banner for operation feedback."""
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
            text="Awaiting System Initialization",
            font=FONT_BODY_BOLD,
            bg=BG_CARD_ALT,
            fg=TEXT_SECONDARY,
        )
        self.lbl_banner_title.pack(side="left")

        self.lbl_banner_details = tk.Label(
            self.banner_frame,
            text="Initialize the bank via Dynamic Configuration to begin manual resource evaluation.",
            font=FONT_CAPTION,
            bg=BG_CARD_ALT,
            fg=TEXT_MUTED,
            wraplength=950,
            justify="left",
        )
        self.lbl_banner_details.pack(anchor="w", pady=(PAD_XS, 0))

    def _build_main_layout(self) -> None:
        """Build the split layout: Left controls panel & Right live matrices panel."""
        self.content_container = tk.Frame(self, bg=BG_MAIN)
        self.content_container.pack(fill="both", expand=True, padx=PAD_XL, pady=(0, PAD_XL))

        # Left Column: Customer Selector, Request Form, Release Form, Activity Log
        self.left_col = tk.Frame(self.content_container, bg=BG_MAIN, width=460)
        self.left_col.pack(side="left", fill="both", expand=False, padx=(0, PAD_MD))
        self.left_col.pack_propagate(False)

        # Right Column: Overview KPI card & Scrollable Matrices tables
        self.right_col = tk.Frame(self.content_container, bg=BG_MAIN)
        self.right_col.pack(side="right", fill="both", expand=True)

        # Build subcomponents
        self._build_customer_card(self.left_col)
        self._build_request_card(self.left_col)
        self._build_release_card(self.left_col)
        self._build_activity_card(self.left_col)

        self._build_overview_card(self.right_col)
        self._build_matrices_card(self.right_col)

    # -------------------------------------------------------------------------
    # Left Column Component Builders
    # -------------------------------------------------------------------------

    def _build_customer_card(self, parent: tk.Widget) -> None:
        """Card for dynamic customer selection and selected customer details."""
        card = create_card(parent)
        card.pack(fill="x", pady=(0, PAD_SM))

        # Title row
        title_row = tk.Frame(card, bg=BG_CARD)
        title_row.pack(fill="x", pady=(0, PAD_SM))

        lbl = tk.Label(
            title_row,
            text="CUSTOMER SELECTION",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl.pack(side="left")

        # Combobox selector row
        sel_row = tk.Frame(card, bg=BG_CARD)
        sel_row.pack(fill="x", pady=(0, PAD_SM))

        lbl_cust = tk.Label(
            sel_row,
            text="Active Customer:",
            font=FONT_BODY_BOLD,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_cust.pack(side="left", padx=(0, PAD_SM))

        self.combo_customer = ttk.Combobox(
            sel_row,
            state="readonly",
            font=FONT_BODY,
            width=16,
        )
        self.combo_customer.pack(side="left", fill="x", expand=True)
        self.combo_customer.bind("<<ComboboxSelected>>", self.on_customer_selected)

        # Customer Detail Indicators (Max, Alloc, Need)
        details_box = tk.Frame(card, bg=BG_SIDEBAR, padx=PAD_MD, pady=PAD_SM)
        details_box.pack(fill="x")

        # Configure 3 equal columns for details
        for c in range(3):
            details_box.grid_columnconfigure(c, weight=1)

        # Max Claim
        lbl_max_title = tk.Label(
            details_box,
            text="Maximum Claim",
            font=FONT_CAPTION_BOLD,
            bg=BG_SIDEBAR,
            fg=TEXT_MUTED,
        )
        lbl_max_title.grid(row=0, column=0, sticky="w")
        self.lbl_cust_max = tk.Label(
            details_box,
            text="[—]",
            font=FONT_MONO_BOLD,
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
        )
        self.lbl_cust_max.grid(row=1, column=0, sticky="w")

        # Current Allocation
        lbl_alloc_title = tk.Label(
            details_box,
            text="Current Allocation",
            font=FONT_CAPTION_BOLD,
            bg=BG_SIDEBAR,
            fg=TEXT_MUTED,
        )
        lbl_alloc_title.grid(row=0, column=1, sticky="w")
        self.lbl_cust_alloc = tk.Label(
            details_box,
            text="[—]",
            font=FONT_MONO_BOLD,
            bg=BG_SIDEBAR,
            fg=ACCENT_PRIMARY,
        )
        self.lbl_cust_alloc.grid(row=1, column=1, sticky="w")

        # Remaining Need
        lbl_need_title = tk.Label(
            details_box,
            text="Remaining Need",
            font=FONT_CAPTION_BOLD,
            bg=BG_SIDEBAR,
            fg=TEXT_MUTED,
        )
        lbl_need_title.grid(row=0, column=2, sticky="w")
        self.lbl_cust_need = tk.Label(
            details_box,
            text="[—]",
            font=FONT_MONO_BOLD,
            bg=BG_SIDEBAR,
            fg=ACCENT_WARNING,
        )
        self.lbl_cust_need.grid(row=1, column=2, sticky="w")

    def _build_request_card(self, parent: tk.Widget) -> None:
        """Card with dynamic inputs to submit customer resource requests."""
        card = create_card(parent)
        card.pack(fill="x", pady=(0, PAD_SM))

        # Title row
        title_row = tk.Frame(card, bg=BG_CARD)
        title_row.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            title_row,
            text="REQUEST RESOURCES",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=ACCENT_PRIMARY,
        )
        lbl.pack(side="left")

        lbl_hint = tk.Label(
            title_row,
            text="Tested against Need and Available pool",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_hint.pack(side="right")

        # Dynamic inputs container
        self.req_inputs_frame = tk.Frame(card, bg=BG_CARD)
        self.req_inputs_frame.pack(fill="x", pady=PAD_SM)

        # Action buttons row
        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.pack(fill="x")

        self.btn_submit_req = ttk.Button(
            btn_row,
            text="Submit Request",
            style="Primary.TButton",
            command=self.submit_request,
        )
        self.btn_submit_req.pack(side="left", padx=(0, PAD_SM))

        btn_fill_need = ttk.Button(
            btn_row,
            text="Fill Max Need",
            style="Secondary.TButton",
            command=self.fill_request_with_need,
        )
        btn_fill_need.pack(side="left", padx=(0, PAD_SM))

        btn_clear_req = ttk.Button(
            btn_row,
            text="Clear",
            style="Secondary.TButton",
            command=self.clear_request_inputs,
        )
        btn_clear_req.pack(side="left")

    def _build_release_card(self, parent: tk.Widget) -> None:
        """Card with dynamic inputs to release allocated resources back to pool."""
        card = create_card(parent)
        card.pack(fill="x", pady=(0, PAD_SM))

        # Title row
        title_row = tk.Frame(card, bg=BG_CARD)
        title_row.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            title_row,
            text="RELEASE RESOURCES",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=ACCENT_SUCCESS,
        )
        lbl.pack(side="left")

        lbl_hint = tk.Label(
            title_row,
            text="Cannot release more than allocated",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_hint.pack(side="right")

        # Dynamic inputs container
        self.rel_inputs_frame = tk.Frame(card, bg=BG_CARD)
        self.rel_inputs_frame.pack(fill="x", pady=PAD_SM)

        # Action buttons row
        btn_row = tk.Frame(card, bg=BG_CARD)
        btn_row.pack(fill="x")

        self.btn_submit_rel = ttk.Button(
            btn_row,
            text="Submit Release",
            style="Secondary.TButton",
            command=self.submit_release,
        )
        self.btn_submit_rel.pack(side="left", padx=(0, PAD_SM))

        btn_fill_alloc = ttk.Button(
            btn_row,
            text="Release All",
            style="Secondary.TButton",
            command=self.fill_release_with_alloc,
        )
        btn_fill_alloc.pack(side="left", padx=(0, PAD_SM))

        btn_clear_rel = ttk.Button(
            btn_row,
            text="Clear",
            style="Secondary.TButton",
            command=self.clear_release_inputs,
        )
        btn_clear_rel.pack(side="left")

    def _build_activity_card(self, parent: tk.Widget) -> None:
        """Compact activity history stream for audit logging."""
        card = create_card(parent)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", pady=(0, PAD_XS))

        lbl_act = tk.Label(
            header,
            text="ACTIVITY FEED",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_act.pack(side="left")

        self.lbl_event_count = tk.Label(
            header,
            text="0 events",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        self.lbl_event_count.pack(side="right")

        # Text stream
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

        # Configure tag colors
        self.txt_log.tag_configure("timestamp", foreground=TEXT_MUTED, font=FONT_MONO_SM)
        self.txt_log.tag_configure("text_normal", foreground=TEXT_PRIMARY, font=FONT_MONO)
        self.txt_log.tag_configure("text_muted", foreground=TEXT_SECONDARY, font=FONT_MONO)
        self.txt_log.tag_configure("accent", foreground=ACCENT_PRIMARY, font=FONT_MONO_BOLD)

        for tag_name, (bg_c, fg_c) in LOG_COLORS.items():
            self.txt_log.tag_configure(
                f"badge_{tag_name}",
                background=bg_c,
                foreground=fg_c,
                font=FONT_MONO_BOLD,
                spacing1=1,
                spacing3=1,
            )

    # -------------------------------------------------------------------------
    # Right Column Component Builders
    # -------------------------------------------------------------------------

    def _build_overview_card(self, parent: tk.Widget) -> None:
        """Card displaying Available Pool and current Safety status."""
        card = create_card(parent)
        card.pack(fill="x", pady=(0, PAD_SM))

        top_line = tk.Frame(card, bg=BG_CARD)
        top_line.pack(fill="x", pady=(0, PAD_SM))

        lbl_sec = tk.Label(
            top_line,
            text="SYSTEM SAFETY & AVAILABLE POOL",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_sec.pack(side="left")

        # KPI Metrics Row
        kpi_row = tk.Frame(card, bg=BG_CARD)
        kpi_row.pack(fill="x")

        # Safety badge
        self.badge_safety_status = tk.Label(
            kpi_row,
            text="● Unchecked",
            font=FONT_BODY_BOLD,
            bg=BORDER_COLOR,
            fg=TEXT_PRIMARY,
            padx=PAD_MD,
            pady=3,
        )
        self.badge_safety_status.pack(side="left", padx=(0, PAD_MD))

        # Safe sequence display
        lbl_seq_title = tk.Label(
            kpi_row,
            text="Safe Sequence:",
            font=FONT_CAPTION_BOLD,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
        )
        lbl_seq_title.pack(side="left", padx=(0, PAD_XS))

        self.lbl_safe_sequence = tk.Label(
            kpi_row,
            text="—",
            font=FONT_MONO_BOLD,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        self.lbl_safe_sequence.pack(side="left", padx=(0, PAD_LG))

        # Available pool chips container
        self.avail_chips_frame = tk.Frame(card, bg=BG_CARD)
        self.avail_chips_frame.pack(fill="x", pady=(PAD_SM, 0))

    def _build_matrices_card(self, parent: tk.Widget) -> None:
        """Card containing scrollable Allocation, Maximum, and Need matrices."""
        card = create_card(parent)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", pady=(0, PAD_XS))

        lbl = tk.Label(
            header,
            text="LIVE STATE MATRICES (C Backend Authority)",
            font=FONT_CARD_TITLE,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl.pack(side="left")

        lbl_hl = tk.Label(
            header,
            text="● Blue highlight indicates currently selected customer",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=ACCENT_INFO,
        )
        lbl_hl.pack(side="right")

        # Scrollable Canvas for tables
        canvas_container = tk.Frame(card, bg=BG_CARD)
        canvas_container.pack(fill="both", expand=True, pady=(PAD_XS, 0))

        self.matrix_canvas = tk.Canvas(
            canvas_container,
            bg=BG_CARD,
            bd=0,
            highlightthickness=0,
        )
        v_scroll = ttk.Scrollbar(
            canvas_container, orient="vertical", command=self.matrix_canvas.yview
        )
        h_scroll = ttk.Scrollbar(
            canvas_container, orient="horizontal", command=self.matrix_canvas.xview
        )

        self.matrix_scroll_content = tk.Frame(self.matrix_canvas, bg=BG_CARD)

        self.matrix_canvas.create_window((0, 0), window=self.matrix_scroll_content, anchor="nw")
        self.matrix_canvas.configure(
            xscrollcommand=h_scroll.set,
            yscrollcommand=v_scroll.set,
        )

        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.matrix_canvas.pack(side="left", fill="both", expand=True)

        def _on_mat_config(event: tk.Event) -> None:
            self.matrix_canvas.configure(scrollregion=self.matrix_canvas.bbox("all"))

        self.matrix_scroll_content.bind("<Configure>", _on_mat_config)

    # =========================================================================
    # Dynamic Input Generation (Part 3 & Part 4)
    # =========================================================================

    def _build_dynamic_inputs(self, num_resources: int) -> None:
        """
        Dynamically generate numeric entry fields for $m$ resource types.

        Generates fields for both Request and Release cards.
        """
        # 1. Clear existing request input entries
        for w in self.req_inputs_frame.winfo_children():
            w.destroy()
        self.req_entries.clear()

        # 2. Clear existing release input entries
        for w in self.rel_inputs_frame.winfo_children():
            w.destroy()
        self.rel_entries.clear()

        if num_resources <= 0:
            return

        # Build Request entries row
        req_row = tk.Frame(self.req_inputs_frame, bg=BG_CARD)
        req_row.pack(fill="x")

        for j in range(num_resources):
            cell = tk.Frame(req_row, bg=BG_CARD)
            cell.pack(side="left", padx=(0, PAD_SM))

            lbl_r = tk.Label(
                cell,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=ACCENT_PRIMARY,
            )
            lbl_r.pack(anchor="w")

            ent = tk.Entry(
                cell,
                width=5,
                justify="center",
                font=FONT_MONO_BOLD,
                bg=BG_SIDEBAR,
                fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY,
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
            )
            ent.insert(0, "0")
            ent.pack(pady=(2, 0))
            self.req_entries.append(ent)

        # Build Release entries row
        rel_row = tk.Frame(self.rel_inputs_frame, bg=BG_CARD)
        rel_row.pack(fill="x")

        for j in range(num_resources):
            cell = tk.Frame(rel_row, bg=BG_CARD)
            cell.pack(side="left", padx=(0, PAD_SM))

            lbl_r = tk.Label(
                cell,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=ACCENT_SUCCESS,
            )
            lbl_r.pack(anchor="w")

            ent = tk.Entry(
                cell,
                width=5,
                justify="center",
                font=FONT_MONO_BOLD,
                bg=BG_SIDEBAR,
                fg=TEXT_PRIMARY,
                insertbackground=TEXT_PRIMARY,
                bd=0,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
            )
            ent.insert(0, "0")
            ent.pack(pady=(2, 0))
            self.rel_entries.append(ent)

    # =========================================================================
    # Dynamic Live State Matrices Display (Part 5)
    # =========================================================================

    def _render_matrices(
        self,
        customers: int,
        resources: int,
        allocation: List[List[int]],
        maximum: List[List[int]],
        need: List[List[int]],
    ) -> None:
        """
        Render Allocation, Maximum, and Need matrix tables inside scrollable area.

        Rebuilds widgets when dimensions change and highlights the active customer row.
        """
        for w in self.matrix_scroll_content.winfo_children():
            w.destroy()

        self._matrix_labels = {
            "allocation": [],
            "maximum": [],
            "need": [],
        }

        # Grid layout holding the 3 tables side-by-side or stacked
        tables_wrapper = tk.Frame(self.matrix_scroll_content, bg=BG_CARD)
        tables_wrapper.pack(fill="both", expand=True)

        # Render Table Helper
        def _render_single_matrix(
            parent_frame: tk.Widget,
            title: str,
            accent_color: str,
            matrix_data: List[List[int]],
            store_key: str,
        ) -> None:
            container = tk.Frame(
                parent_frame,
                bg=BG_SIDEBAR,
                highlightthickness=1,
                highlightbackground=BORDER_COLOR,
                padx=PAD_SM,
                pady=PAD_SM,
            )
            container.pack(side="left", fill="both", expand=True, padx=(0, PAD_MD))

            lbl_tbl_title = tk.Label(
                container,
                text=title,
                font=FONT_BODY_BOLD,
                bg=BG_SIDEBAR,
                fg=accent_color,
            )
            lbl_tbl_title.pack(anchor="w", pady=(0, PAD_XS))

            grid = tk.Frame(container, bg=BG_SIDEBAR)
            grid.pack(fill="both", expand=True)

            # Header row
            lbl_corner = tk.Label(
                grid, text="Cust", font=FONT_CAPTION_BOLD, bg=BG_SIDEBAR, fg=TEXT_MUTED
            )
            lbl_corner.grid(row=0, column=0, padx=2, pady=2, sticky="w")

            for j in range(resources):
                lbl_h = tk.Label(
                    grid,
                    text=f"R{j}",
                    font=FONT_CARD_TITLE,
                    bg=BG_SIDEBAR,
                    fg=accent_color,
                    width=4,
                )
                lbl_h.grid(row=0, column=j + 1, padx=2, pady=2)

            # Data rows
            row_labels_list: List[List[tk.Label]] = []
            for i in range(customers):
                row_cells: List[tk.Label] = []
                lbl_row_id = tk.Label(
                    grid,
                    text=f"C{i}",
                    font=FONT_CAPTION_BOLD,
                    bg=BG_SIDEBAR,
                    fg=TEXT_SECONDARY,
                    width=4,
                    anchor="w",
                )
                lbl_row_id.grid(row=i + 1, column=0, padx=2, pady=2, sticky="w")
                row_cells.append(lbl_row_id)

                row_vals = matrix_data[i] if i < len(matrix_data) else []
                for j in range(resources):
                    val = row_vals[j] if j < len(row_vals) else 0
                    lbl_cell = tk.Label(
                        grid,
                        text=str(val),
                        font=FONT_MONO,
                        bg=BG_CARD_ALT,
                        fg=TEXT_PRIMARY,
                        width=4,
                        highlightthickness=1,
                        highlightbackground=BORDER_COLOR,
                        pady=1,
                    )
                    lbl_cell.grid(row=i + 1, column=j + 1, padx=2, pady=2)
                    row_cells.append(lbl_cell)

                row_labels_list.append(row_cells)

            self._matrix_labels[store_key] = row_labels_list

        # Render 3 Matrices: Allocation, Need, and Maximum
        _render_single_matrix(
            tables_wrapper,
            title="Allocation Matrix",
            accent_color=ACCENT_PRIMARY,
            matrix_data=allocation,
            store_key="allocation",
        )

        _render_single_matrix(
            tables_wrapper,
            title="Need Matrix (Max - Alloc)",
            accent_color=ACCENT_WARNING,
            matrix_data=need,
            store_key="need",
        )

        _render_single_matrix(
            tables_wrapper,
            title="Maximum Matrix",
            accent_color=ACCENT_INFO,
            matrix_data=maximum,
            store_key="maximum",
        )

        # Highlight the currently active customer row
        self._highlight_selected_customer_row()

    def _highlight_selected_customer_row(self) -> None:
        """Highlight matrix rows corresponding to the active customer."""
        sel_idx = self._selected_customer_idx

        for key, rows in self._matrix_labels.items():
            for i, row_cells in enumerate(rows):
                is_selected = i == sel_idx
                for c_idx, cell in enumerate(row_cells):
                    if is_selected:
                        # Row header vs value cell
                        if c_idx == 0:
                            cell.configure(bg=ACCENT_PRIMARY_BG, fg="#FFFFFF")
                        else:
                            cell.configure(
                                bg=ACCENT_PRIMARY_BG,
                                fg="#FFFFFF",
                                font=FONT_MONO_BOLD,
                                highlightbackground=ACCENT_PRIMARY,
                            )
                    else:
                        if c_idx == 0:
                            cell.configure(bg=BG_SIDEBAR, fg=TEXT_SECONDARY)
                        else:
                            cell.configure(
                                bg=BG_CARD_ALT,
                                fg=TEXT_PRIMARY,
                                font=FONT_MONO,
                                highlightbackground=BORDER_COLOR,
                            )

    # =========================================================================
    # Customer Selection Handling (Part 2)
    # =========================================================================

    def on_customer_selected(self, event: Optional[tk.Event] = None) -> None:
        """Triggered when user changes the active customer in the dropdown."""
        val = self.combo_customer.get().strip()
        if not val or not val.startswith("Customer C"):
            return

        try:
            cust_idx = int(val.replace("Customer C", ""))
            self._selected_customer_idx = cust_idx
            self._update_customer_details()
            self._highlight_selected_customer_row()
            self._log_activity("SELECT", f"Active customer changed to Customer C{cust_idx}.")
        except ValueError:
            pass

    def _update_customer_details(self) -> None:
        """Refresh selected customer's Maximum, Allocation, and Need vector labels."""
        if not self._current_snapshot:
            self.lbl_cust_max.configure(text="[—]")
            self.lbl_cust_alloc.configure(text="[—]")
            self.lbl_cust_need.configure(text="[—]")
            return

        c = self._selected_customer_idx
        alloc = self._current_snapshot.get("allocation", [])
        maximum = self._current_snapshot.get("maximum", [])
        need = self._current_snapshot.get("need", [])

        c_max = maximum[c] if c < len(maximum) else []
        c_alloc = alloc[c] if c < len(alloc) else []
        c_need = need[c] if c < len(need) else []

        self.lbl_cust_max.configure(text=str(c_max))
        self.lbl_cust_alloc.configure(text=str(c_alloc))
        self.lbl_cust_need.configure(text=str(c_need))

    # =========================================================================
    # Request & Release User Actions (Part 3 & Part 4)
    # =========================================================================

    def submit_request(self) -> None:
        """
        Validate input fields and dispatch 'request' command to backend.

        Guards against duplicate submissions while request is pending.
        """
        if self._pending_op is not None:
            logger.warning("Operation already pending: %s", self._pending_op)
            return

        if not self._is_initialized or not self._current_snapshot:
            self.set_status("Cannot request: System is not initialized.", variant="danger")
            return

        if not self.client.is_running():
            self.set_status("Cannot request: Backend process is not running.", variant="danger")
            return

        c = self._selected_customer_idx
        m = self._current_snapshot.get("resources", len(self.req_entries))
        req_vector: List[int] = []

        for j, ent in enumerate(self.req_entries):
            raw = ent.get().strip()
            if not raw:
                raw = "0"
            try:
                v = int(raw)
                if v < 0:
                    raise ValueError()
                req_vector.append(v)
            except ValueError:
                self.set_status(
                    f"Invalid request entry for R{j}. All values must be nonnegative integers.",
                    variant="danger",
                )
                return

        # Lock UI to prevent duplicate submissions
        self._pending_op = "request"
        self._pending_customer = c
        self._pending_vector = req_vector

        self.btn_submit_req.configure(state="disabled", text="Requesting...")
        self.btn_submit_rel.configure(state="disabled")

        self.set_status(
            f"Submitting request {req_vector} for Customer C{c} to C backend...",
            variant="info",
        )
        self._log_activity("REQUEST", f"Dispatched request for C{c}: {req_vector}")

        try:
            self.client.request(c, req_vector)
        except Exception as e:
            self._pending_op = None
            self.btn_submit_req.configure(state="normal", text="Submit Request")
            self.btn_submit_rel.configure(state="normal", text="Submit Release")
            self.set_status(f"Failed to transmit request: {e}", variant="danger")

    def submit_release(self) -> None:
        """
        Validate input fields and dispatch 'release' command to backend.

        Enforces client-side validation that release amount does not exceed
        current customer allocation.
        """
        if self._pending_op is not None:
            logger.warning("Operation already pending: %s", self._pending_op)
            return

        if not self._is_initialized or not self._current_snapshot:
            self.set_status("Cannot release: System is not initialized.", variant="danger")
            return

        if not self.client.is_running():
            self.set_status("Cannot release: Backend process is not running.", variant="danger")
            return

        c = self._selected_customer_idx
        m = self._current_snapshot.get("resources", len(self.rel_entries))
        alloc_matrix = self._current_snapshot.get("allocation", [])
        c_alloc = alloc_matrix[c] if c < len(alloc_matrix) else [0] * m

        rel_vector: List[int] = []
        for j, ent in enumerate(self.rel_entries):
            raw = ent.get().strip()
            if not raw:
                raw = "0"
            try:
                v = int(raw)
                if v < 0:
                    raise ValueError()
            except ValueError:
                self.set_status(
                    f"Invalid release entry for R{j}. All values must be nonnegative integers.",
                    variant="danger",
                )
                return

            # Client-side validation: cannot release more than currently held
            alloc_j = c_alloc[j] if j < len(c_alloc) else 0
            if v > alloc_j:
                self.set_status(
                    f"Release Rejected: Customer C{c} holds {alloc_j} of R{j}, cannot release {v}.",
                    variant="danger",
                    details=f"Current allocation for C{c} is {c_alloc}. System state unchanged.",
                )
                self._log_activity(
                    "ERROR",
                    f"Release rejected: C{c} holds {alloc_j} of R{j}, attempted release of {v}.",
                )
                return

            rel_vector.append(v)

        # Lock UI
        self._pending_op = "release"
        self._pending_customer = c
        self._pending_vector = rel_vector

        self.btn_submit_rel.configure(state="disabled", text="Releasing...")
        self.btn_submit_req.configure(state="disabled")

        self.set_status(
            f"Submitting release {rel_vector} for Customer C{c} to C backend...",
            variant="info",
        )
        self._log_activity("RELEASE", f"Dispatched release for C{c}: {rel_vector}")

        try:
            self.client.release(c, rel_vector)
        except Exception as e:
            self._pending_op = None
            self.btn_submit_rel.configure(state="normal", text="Submit Release")
            self.btn_submit_req.configure(state="normal", text="Submit Request")
            self.set_status(f"Failed to transmit release: {e}", variant="danger")

    def fill_request_with_need(self) -> None:
        """Fill request input fields with the active customer's current Need vector."""
        if not self._current_snapshot:
            return
        c = self._selected_customer_idx
        need = self._current_snapshot.get("need", [])
        c_need = need[c] if c < len(need) else []

        for j, ent in enumerate(self.req_entries):
            val = c_need[j] if j < len(c_need) else 0
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

    def fill_release_with_alloc(self) -> None:
        """Fill release input fields with the active customer's current Allocation vector."""
        if not self._current_snapshot:
            return
        c = self._selected_customer_idx
        alloc = self._current_snapshot.get("allocation", [])
        c_alloc = alloc[c] if c < len(alloc) else []

        for j, ent in enumerate(self.rel_entries):
            val = c_alloc[j] if j < len(c_alloc) else 0
            ent.delete(0, tk.END)
            ent.insert(0, str(val))

    def clear_request_inputs(self) -> None:
        """Reset all request inputs to 0."""
        for ent in self.req_entries:
            ent.delete(0, tk.END)
            ent.insert(0, "0")

    def clear_release_inputs(self) -> None:
        """Reset all release inputs to 0."""
        for ent in self.rel_entries:
            ent.delete(0, tk.END)
            ent.insert(0, "0")

    # =========================================================================
    # Backend Queue Polling & Protocol Message Dispatch
    # =========================================================================

    def _poll_backend_queue(self) -> None:
        """Non-blocking message consumption loop executed on Tkinter thread."""
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
        """Dispatch backend response JSON to specific outcome handlers."""
        status = msg.get("status")

        # 1. Error message
        if status == "error":
            err_msg = msg.get("message", "Unknown error from backend")
            self._handle_error_response(err_msg)
            return

        # 2. Request outcome message
        if status in ("granted", "unsafe", "exceeds_need", "unavailable", "invalid") and (
            self._pending_op == "request" or "safe_sequence" in msg
        ):
            self._handle_request_outcome(status, msg)
            return

        # 3. Release outcome message
        if status == "released" or (status == "invalid" and self._pending_op == "release"):
            self._handle_release_outcome(status, msg)
            return

        # 4. Snapshot response
        if status == "ok" and "customers" in msg and "resources" in msg and "available" in msg:
            self._apply_snapshot(msg)
            return

        # 5. Initialization / Reset ack
        if status == "ok" and msg.get("message") == "Bank initialized":
            self._is_initialized = True
            self.refresh_snapshot()
            return

        if status == "ok" and msg.get("message") == "Bank reset":
            self._render_uninitialized_state()
            self._log_activity("RESET", "Bank reset to uninitialized state.")
            return

    def _handle_request_outcome(self, status: str, msg: Dict[str, Any]) -> None:
        """Handle outcome of a resource request command."""
        c = self._pending_customer if self._pending_customer is not None else self._selected_customer_idx
        req = self._pending_vector or []
        seq = msg.get("safe_sequence", [])
        seq_str = " → ".join(f"C{x}" for x in seq) if seq else "None"

        # Re-enable action buttons
        self._pending_op = None
        self.btn_submit_req.configure(state="normal", text="Submit Request")
        self.btn_submit_rel.configure(state="normal", text="Submit Release")

        if status == "granted":
            self.set_status(
                f"REQUEST GRANTED: State remains safe. Safe sequence: {seq_str}",
                variant="success",
                details=f"Allocated {req} to Customer C{c}. System state updated successfully.",
            )
            self._log_activity(
                "GRANTED", f"Request for C{c} granted: {req}. Safe sequence: {seq_str}"
            )

        elif status == "unsafe":
            self.set_status(
                f"REQUEST DENIED — UNSAFE STATE: Deadlock risk detected.",
                variant="warning",
                details=(
                    f"Granting request {req} to Customer C{c} would leave the system with no safe execution "
                    f"pathway (deadlock hazard). The backend rolled back the tentative allocation. State is unchanged."
                ),
            )
            self._log_activity(
                "UNSAFE",
                f"Request denied (unsafe): C{c} requested {req}. Tentative allocation rolled back.",
            )

        elif status == "exceeds_need":
            self.set_status(
                f"REQUEST DENIED — EXCEEDS NEED: Customer C{c} exceeded declared claim.",
                variant="danger",
                details=(
                    f"Request {req} exceeds Customer C{c}'s declared remaining need vector. "
                    "A customer cannot claim more than its declared maximum. System state unchanged."
                ),
            )
            self._log_activity(
                "EXCEEDS",
                f"Request denied: C{c} requested {req}, which exceeds remaining Need.",
            )

        elif status == "unavailable":
            avail = self._current_snapshot.get("available", []) if self._current_snapshot else []
            self.set_status(
                f"REQUEST DENIED — RESOURCES UNAVAILABLE: Pool capacity exceeded.",
                variant="warning",
                details=(
                    f"Customer C{c} requested {req}, but available pool is {avail}. "
                    "Customer must wait until other processes release resources. System state unchanged."
                ),
            )
            self._log_activity(
                "UNAVAIL",
                f"Request denied: Requested {req} exceeds available pool {avail}.",
            )

        else:  # "invalid"
            self.set_status(
                "REQUEST DENIED — INVALID REQUEST: Backend rejected parameters.",
                variant="danger",
                details="The backend reported invalid customer index or negative resource quantities.",
            )
            self._log_activity("ERROR", f"Invalid request parameters for Customer C{c}.")

    def _handle_release_outcome(self, status: str, msg: Dict[str, Any]) -> None:
        """Handle outcome of a resource release command."""
        c = self._pending_customer if self._pending_customer is not None else self._selected_customer_idx
        rel = self._pending_vector or []

        # Re-enable action buttons
        self._pending_op = None
        self.btn_submit_rel.configure(state="normal", text="Submit Release")
        self.btn_submit_req.configure(state="normal", text="Submit Request")

        if status == "released":
            self.set_status(
                f"RESOURCES RELEASED: Customer C{c} returned resources to available pool.",
                variant="success",
                details=f"Successfully released {rel} from Customer C{c}. Available pool expanded.",
            )
            self._log_activity("RELEASE", f"Customer C{c} released: {rel}")
        else:
            self.set_status(
                f"RELEASE FAILED: Invalid release parameters.",
                variant="danger",
                details="Cannot release more resources than currently allocated.",
            )
            self._log_activity("ERROR", f"Release failed for C{c}: {rel}")

    def _handle_error_response(self, err_msg: str) -> None:
        """Handle generic backend error."""
        self._pending_op = None
        self.btn_submit_req.configure(state="normal", text="Submit Request")
        self.btn_submit_rel.configure(state="normal", text="Submit Release")

        if "not initialized" in err_msg.lower():
            self._render_uninitialized_state()
            self.set_status("Bank is not initialized. Please configure the system first.", variant="warning")
            self._log_activity("ERROR", "Backend reported: Bank is not initialized.")
        else:
            self.set_status(f"Backend Error: {err_msg}", variant="danger")
            self._log_activity("ERROR", f"Backend error: {err_msg}")

    # =========================================================================
    # Snapshot Application (Part 5)
    # =========================================================================

    def _apply_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Apply live snapshot from C backend to all UI indicators and matrices."""
        self._current_snapshot = snapshot
        self._is_initialized = True

        customers = snapshot.get("customers", 0)
        resources = snapshot.get("resources", 0)
        available = snapshot.get("available", [])
        allocation = snapshot.get("allocation", [])
        maximum = snapshot.get("maximum", [])
        need = snapshot.get("need", [])
        is_safe = snapshot.get("safe", False)
        safe_seq = snapshot.get("safe_sequence", [])

        # Update Header State Badge
        if is_safe:
            self.badge_state.configure(
                text="System Active (Safe)", bg=ACCENT_SUCCESS_BG, fg="#86EFAC"
            )
        else:
            self.badge_state.configure(
                text="System Active (Unsafe)", bg=ACCENT_DANGER_BG, fg="#FCA5A5"
            )

        # Update Overview KPI Card
        if is_safe:
            self.badge_safety_status.configure(
                text="● SAFE STATE", bg=ACCENT_SUCCESS_BG, fg="#86EFAC"
            )
            seq_display = " → ".join(f"C{x}" for x in safe_seq) if safe_seq else "Empty"
            self.lbl_safe_sequence.configure(text=seq_display, fg="#86EFAC")
        else:
            self.badge_safety_status.configure(
                text="● UNSAFE STATE", bg=ACCENT_DANGER_BG, fg="#FCA5A5"
            )
            self.lbl_safe_sequence.configure(text="None (Deadlock Risk)", fg="#FCA5A5")

        # Update Available Pool chips
        for w in self.avail_chips_frame.winfo_children():
            w.destroy()

        lbl_av_title = tk.Label(
            self.avail_chips_frame,
            text="Available Pool:",
            font=FONT_CAPTION_BOLD,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
        )
        lbl_av_title.pack(side="left", padx=(0, PAD_SM))

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

            tk.Label(
                chip,
                text=f"R{j}: ",
                font=FONT_CAPTION_BOLD,
                bg=BG_SIDEBAR,
                fg=ACCENT_PRIMARY,
            ).pack(side="left")

            tk.Label(
                chip,
                text=str(val),
                font=FONT_MONO_BOLD,
                bg=BG_SIDEBAR,
                fg=TEXT_PRIMARY,
            ).pack(side="left")

        # Update Customer Selector values
        expected_values = [f"Customer C{i}" for i in range(customers)]
        current_values = list(self.combo_customer["values"])
        if current_values != expected_values:
            self.combo_customer["values"] = expected_values
            if self._selected_customer_idx >= customers:
                self._selected_customer_idx = 0
            if expected_values:
                self.combo_customer.current(self._selected_customer_idx)

        # Update selected customer details
        self._update_customer_details()

        # Update dynamic input entries if resource count changed
        if len(self.req_entries) != resources:
            self._build_dynamic_inputs(resources)

        # Render matrices
        self._render_matrices(customers, resources, allocation, maximum, need)

        # Log snapshot receipt if not a sub-step of request/release
        if self._pending_op is None:
            self._log_activity(
                "SNAPSHOT",
                f"State synced: Customers={customers}, Resources={resources}, Safe={is_safe}, Available={available}",
            )

    def _render_uninitialized_state(self) -> None:
        """Render UI when bank backend is not yet initialized."""
        self._is_initialized = False
        self._current_snapshot = None

        self.badge_state.configure(text="Uninitialized", bg=ACCENT_WARNING_BG, fg="#FDE047")
        self.badge_safety_status.configure(text="● Uninitialized", bg=BORDER_COLOR, fg=TEXT_MUTED)
        self.lbl_safe_sequence.configure(text="—", fg=TEXT_MUTED)

        self.combo_customer["values"] = []
        self.combo_customer.set("")

        self.lbl_cust_max.configure(text="[—]")
        self.lbl_cust_alloc.configure(text="[—]")
        self.lbl_cust_need.configure(text="[—]")

        for w in self.avail_chips_frame.winfo_children():
            w.destroy()
        lbl_msg = tk.Label(
            self.avail_chips_frame,
            text="No active resource pool. Bank must be initialized.",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_msg.pack(side="left")

        for w in self.matrix_scroll_content.winfo_children():
            w.destroy()
        lbl_mat_msg = tk.Label(
            self.matrix_scroll_content,
            text="System state matrices will appear here once the bank is initialized.",
            font=FONT_BODY,
            bg=BG_CARD,
            fg=TEXT_MUTED,
            pady=PAD_2XL,
        )
        lbl_mat_msg.pack(anchor="center")

    # =========================================================================
    # Activity Stream Logger (Part 6)
    # =========================================================================

    def _log_activity(self, tag: str, text: str) -> None:
        """Append a colored event to the activity log."""
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
        """Update top outcome banner styling and content."""
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
    # Navigation & Lifecycle (Part 7)
    # =========================================================================

    def refresh_snapshot(self) -> None:
        """Dispatch snapshot request to C backend."""
        if not self.client.is_running():
            self.set_status("Cannot refresh: Backend is not running.", variant="danger")
            return
        try:
            self.client.snapshot()
        except Exception as e:
            self.set_status(f"Failed to request snapshot: {e}", variant="danger")

    def navigate_to_dashboard(self) -> None:
        """Return to main dashboard using application controller callback."""
        if self.on_navigate_dashboard:
            try:
                self.on_navigate_dashboard()
            except Exception as e:
                logger.error("Navigation error: %s", e)
        else:
            self._log_activity("INFO", "Dashboard navigation triggered (standalone mode).")

    def navigate_to_automatic(self) -> None:
        """Switch to Automatic Mode using application controller callback."""
        if self.on_navigate_automatic:
            try:
                self.on_navigate_automatic()
            except Exception as e:
                logger.error("Navigation error: %s", e)
        else:
            self._log_activity("INFO", "Automatic Mode navigation triggered (standalone mode).")

    def pause_polling(self) -> None:
        """Pause queue polling when Manual Mode frame is hidden."""
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
        """Called when Manual Mode screen becomes visible."""
        self.resume_polling()

    def destroy(self) -> None:
        """Clean up pending callbacks upon destruction."""
        self.pause_polling()
        super().destroy()


# =============================================================================
# Standalone Testing Launcher
# =============================================================================
def main() -> None:
    """Launch ManualMode directly for interactive testing."""
    root = tk.Tk()
    root.title("Banker's Algorithm Simulator — Manual Mode")
    root.geometry("1100x750")
    root.minsize(960, 620)
    setup_styles(root)

    client = BackendClient()
    try:
        client.start()
    except Exception as e:
        print("Backend startup failed:", e)

    frame = ManualModeFrame(root, client=client)
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

