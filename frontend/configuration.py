"""
configuration.py: Dynamic Configuration screen for Banker's Algorithm Simulator.

Allows users to configure:
- Dynamic simulation dimensions (1-50 customers, 1-10 resource types).
- Total system resource capacities.
- Maximum claim matrix (Max).
- Current allocation matrix (Alloc).
- Comprehensive client-side validation (non-negativity, Alloc <= Max, sum(Alloc) <= Total).
- Protocol-compliant backend initialization via BackendClient.
- Rich success feedback with live backend calculated results (Available, Need, Safety, Safe Sequence).
- Duplicate-click prevention while initialization is in-flight.
"""

from __future__ import annotations

import logging
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    ACCENT_PRIMARY_HOVER,
    ACCENT_SUCCESS,
    ACCENT_SUCCESS_BG,
    ACCENT_SUCCESS_HOVER,
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

logger = logging.getLogger("bankers.configuration")

# Dimension constraints discovered from C backend (banker.c, protocol.c)
MIN_CUSTOMERS = 1
MAX_CUSTOMERS = 50
MIN_RESOURCES = 1
MAX_RESOURCES = 10
MAX_RESOURCE_CAPACITY = 1000


class ConfigurationFrame(tk.Frame):
    """
    Dynamic Configuration Frame for the Banker's Algorithm Simulator.

    Handles:
    1. Simulation dimension inputs (Customers: 1-50, Resources: 1-10).
    2. Dynamic generation of Total vector and (Customer x Resource) matrices.
    3. Input validation (positive integers, non-negative values, Alloc <= Max, Sum(Alloc) <= Total).
    4. Building and sending exact backend 'initialize' JSON command.
    5. Asynchronous, non-blocking response polling using Tkinter's after() loop.
    6. Prominent success feedback showing backend-calculated results:
       Available vector, Need matrix, SAFE/UNSAFE status, and safe sequence.
    7. Preventing duplicate submissions while initialization is in progress.
    """

    def __init__(
        self,
        master: tk.Widget,
        client: BackendClient,
        on_initialized: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_navigate_dashboard: Optional[Callable[[], None]] = None,
        on_go_to_dashboard: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=BG_MAIN, **kwargs)
        self.client = client
        self.on_initialized = on_initialized
        self.on_navigate_dashboard = on_navigate_dashboard or on_go_to_dashboard
        self.on_go_to_dashboard = self.on_navigate_dashboard

        # Form state
        self._init_pending = False
        self._poll_deadline = 0.0
        self._last_snapshot: Optional[Dict[str, Any]] = None

        # Grid Entry Widget references
        self.total_entries: List[tk.Entry] = []
        self.maximum_entries: List[List[tk.Entry]] = []
        self.allocation_entries: List[List[tk.Entry]] = []

        # Current generated dimensions
        self._current_n = 0
        self._current_m = 0

        # Build UI layout
        self._build_header()
        self._build_dimension_card()
        self._build_status_banner()
        self._build_scrollable_matrix_area()
        self._build_action_bar()

        # Generate default initial matrix (5 customers, 3 resources)
        self.load_preset_5x3()

    # =========================================================================
    # UI Layout Construction
    # =========================================================================

    def _build_header(self) -> None:
        """Build screen header with title and quick preset buttons."""
        header_frame = tk.Frame(self, bg=BG_MAIN)
        header_frame.pack(fill="x", padx=PAD_XL, pady=(PAD_XL, PAD_MD))

        # Title & Subtitle
        title_box = tk.Frame(header_frame, bg=BG_MAIN)
        title_box.pack(side="left", fill="y")

        lbl_title = tk.Label(
            title_box,
            text="Dynamic System Configuration",
            font=FONT_TITLE,
            bg=BG_MAIN,
            fg=TEXT_PRIMARY,
        )
        lbl_title.pack(anchor="w")

        lbl_subtitle = tk.Label(
            title_box,
            text="Define customer counts, resource types, and initial allocation matrices",
            font=FONT_SUBTITLE,
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
        )
        lbl_subtitle.pack(anchor="w", pady=(2, 0))

        # Preset Buttons on the right
        preset_box = tk.Frame(header_frame, bg=BG_MAIN)
        preset_box.pack(side="right", fill="y")

        btn_preset_5x3 = ttk.Button(
            preset_box,
            text="Load 5×3 Preset",
            style="Secondary.TButton",
            command=self.load_preset_5x3,
        )
        btn_preset_5x3.pack(side="left", padx=(0, PAD_SM))

        btn_preset_3x2 = ttk.Button(
            preset_box,
            text="Load 3×2 Preset",
            style="Secondary.TButton",
            command=self.load_preset_3x2,
        )
        btn_preset_3x2.pack(side="left")

    def _build_dimension_card(self) -> None:
        """Build controls card for setting customer and resource type counts."""
        self.dimension_card = create_card(self, padx=PAD_LG, pady=PAD_MD)
        self.dimension_card.pack(fill="x", padx=PAD_XL, pady=(0, PAD_SM))

        inner = tk.Frame(self.dimension_card, bg=BG_CARD)
        inner.pack(fill="x")

        # Customer Count
        lbl_cust = tk.Label(
            inner,
            text="Customers (n):",
            font=FONT_BODY_BOLD,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_cust.pack(side="left", padx=(0, PAD_SM))

        self.customers_var = tk.StringVar(value="5")
        self.entry_customers = tk.Entry(
            inner,
            textvariable=self.customers_var,
            width=5,
            font=FONT_MONO_BOLD,
            justify="center",
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_PRIMARY,
        )
        self.entry_customers.pack(side="left", padx=(0, PAD_LG))

        # Resource Count
        lbl_res = tk.Label(
            inner,
            text="Resources (m):",
            font=FONT_BODY_BOLD,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_res.pack(side="left", padx=(0, PAD_SM))

        self.resources_var = tk.StringVar(value="3")
        self.entry_resources = tk.Entry(
            inner,
            textvariable=self.resources_var,
            width=5,
            font=FONT_MONO_BOLD,
            justify="center",
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_PRIMARY,
        )
        self.entry_resources.pack(side="left", padx=(0, PAD_LG))

        # Generate Button
        btn_generate = ttk.Button(
            inner,
            text="Generate Matrix",
            style="Primary.TButton",
            command=self.generate_matrix_from_inputs,
        )
        btn_generate.pack(side="left", padx=(0, PAD_SM))

        # Clear Button
        btn_clear = ttk.Button(
            inner,
            text="Clear Form",
            style="Secondary.TButton",
            command=self.clear_form,
        )
        btn_clear.pack(side="left", padx=(0, PAD_LG))

        # Dimension constraints label
        lbl_limits = tk.Label(
            inner,
            text=f"Limits: {MIN_CUSTOMERS}–{MAX_CUSTOMERS} customers, {MIN_RESOURCES}–{MAX_RESOURCES} resources, ≤ {MAX_RESOURCE_CAPACITY} instances",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_limits.pack(side="right")

    def _build_status_banner(self) -> None:
        """Build feedback banner for validation errors, warnings, or rich success feedback."""
        self.banner_frame = tk.Frame(self, bg=BG_MAIN)
        self.banner_frame.pack(fill="x", padx=PAD_XL, pady=(0, PAD_SM))

        self.banner_inner = tk.Frame(
            self.banner_frame,
            bg=BG_CARD,
            padx=PAD_MD,
            pady=PAD_SM,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
        )
        self.banner_inner.pack(fill="x")

        # Top row: icon + main status + optional "Go to Dashboard" button
        self.banner_top_row = tk.Frame(self.banner_inner, bg=BG_CARD)
        self.banner_top_row.pack(fill="x")

        self.lbl_status = tk.Label(
            self.banner_top_row,
            text="",
            font=FONT_BODY_BOLD,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            anchor="w",
            justify="left",
        )
        self.lbl_status.pack(side="left", fill="x", expand=True)

        self.btn_banner_dashboard = ttk.Button(
            self.banner_top_row,
            text="Go to Dashboard →",
            style="Success.TButton",
            command=self.go_to_dashboard,
        )
        # Initially unmapped
        self.btn_banner_dashboard.pack_forget()

        # Details label for multi-line summary (Available vector, Safe sequence, etc.)
        self.lbl_banner_details = tk.Label(
            self.banner_inner,
            text="",
            font=FONT_CAPTION,
            bg=BG_CARD,
            fg=TEXT_SECONDARY,
            anchor="w",
            justify="left",
        )
        self.lbl_banner_details.pack(fill="x", pady=(PAD_XS, 0))
        self.lbl_banner_details.pack_forget()

        # Hidden initially
        self.banner_frame.pack_forget()

    def _build_scrollable_matrix_area(self) -> None:
        """Build scrollable viewport for total resources, input matrices, and results."""
        self.matrix_outer = create_card(self, padx=0, pady=0)
        self.matrix_outer.pack(fill="both", expand=True, padx=PAD_XL, pady=(0, PAD_SM))

        # Canvas with custom scrollbars
        self.canvas = tk.Canvas(self.matrix_outer, bg=BG_CARD, highlightthickness=0, bd=0)
        self.scrollbar_y = ttk.Scrollbar(
            self.matrix_outer, orient="vertical", command=self.canvas.yview, style="Vertical.TScrollbar"
        )
        self.scrollbar_x = ttk.Scrollbar(
            self.matrix_outer, orient="horizontal", command=self.canvas.xview
        )

        self.matrix_content = tk.Frame(self.canvas, bg=BG_CARD, padx=PAD_LG, pady=PAD_LG)
        self.matrix_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.matrix_content, anchor="nw"
        )
        self.canvas.configure(xscrollcommand=self.scrollbar_x.set, yscrollcommand=self.scrollbar_y.set)

        self.scrollbar_y.pack(side="right", fill="y")
        self.scrollbar_x.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel binding for smooth vertical scrolling
        def _on_mousewheel(event: tk.Event) -> None:
            if sys.platform == "win32":
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif sys.platform == "darwin":
                self.canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                if event.num == 4:
                    self.canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(1, "units")

        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.canvas.bind_all("<Button-4>", _on_mousewheel)
        self.canvas.bind_all("<Button-5>", _on_mousewheel)

    def _build_action_bar(self) -> None:
        """Build bottom action bar containing Initialize submission button."""
        self.action_bar = tk.Frame(self, bg=BG_MAIN)
        self.action_bar.pack(fill="x", padx=PAD_XL, pady=(0, PAD_XL))

        self.btn_init = ttk.Button(
            self.action_bar,
            text="Initialize Bank",
            style="Primary.TButton",
            command=self.initialize_bank,
        )
        self.btn_init.pack(side="left", padx=(0, PAD_MD))

        # Action bar "Go to Dashboard" button (shown after successful initialization)
        self.btn_action_dashboard = ttk.Button(
            self.action_bar,
            text="Go to Dashboard →",
            style="Success.TButton",
            command=self.go_to_dashboard,
        )
        # Initially hidden
        self.btn_action_dashboard.pack(side="left", padx=(0, PAD_MD))
        self.btn_action_dashboard.pack_forget()

        self.lbl_init_hint = tk.Label(
            self.action_bar,
            text="Validates all matrices client-side, then dispatches dynamic initialization to C backend.",
            font=FONT_CAPTION,
            bg=BG_MAIN,
            fg=TEXT_MUTED,
        )
        self.lbl_init_hint.pack(side="left")

    # =========================================================================
    # Status / Banner Helpers
    # =========================================================================

    def set_status(
        self,
        message: str,
        variant: str = "info",
        details: Optional[str] = None,
        show_dashboard_btn: bool = False,
    ) -> None:
        """
        Display a prominent feedback banner.

        Variants: 'danger', 'success', 'warning', 'info'
        """
        styles_map = {
            "danger": (ACCENT_DANGER_BG, "#FCA5A5", "❌ "),
            "success": (ACCENT_SUCCESS_BG, "#86EFAC", "✔ "),
            "warning": (ACCENT_WARNING_BG, "#FDE047", "⚠ "),
            "info": (ACCENT_PRIMARY_BG, "#93C5FD", "ℹ "),
        }
        bg, fg, icon = styles_map.get(variant, styles_map["info"])

        self.banner_inner.configure(bg=bg, highlightbackground=fg, highlightthickness=1)
        self.banner_top_row.configure(bg=bg)
        self.lbl_status.configure(text=f"{icon}{message}", bg=bg, fg=fg)

        if details:
            self.lbl_banner_details.configure(text=details, bg=bg, fg=fg)
            self.lbl_banner_details.pack(fill="x", pady=(PAD_XS, 0))
        else:
            self.lbl_banner_details.pack_forget()

        if show_dashboard_btn:
            self.btn_banner_dashboard.pack(side="right", padx=(PAD_MD, 0))
        else:
            self.btn_banner_dashboard.pack_forget()

        # Sibling-safe packing directly after dimension_card
        self.banner_frame.pack(
            fill="x",
            padx=PAD_XL,
            pady=(0, PAD_SM),
            after=self.dimension_card,
        )

    def clear_status(self) -> None:
        """Hide the status banner."""
        self.banner_frame.pack_forget()

    # =========================================================================
    # Dynamic Matrix Generation
    # =========================================================================

    def generate_matrix_from_inputs(self) -> None:
        """Read dimension entry fields, validate, and rebuild matrix tables."""
        self.clear_status()
        self._hide_results()
        raw_n = self.customers_var.get().strip()
        raw_m = self.resources_var.get().strip()

        try:
            n = int(raw_n)
            m = int(raw_m)
        except ValueError:
            self.set_status("Customer and Resource counts must be positive integers.", variant="danger")
            return

        if not (MIN_CUSTOMERS <= n <= MAX_CUSTOMERS):
            self.set_status(
                f"Customer count must be between {MIN_CUSTOMERS} and {MAX_CUSTOMERS}.",
                variant="danger",
            )
            return

        if not (MIN_RESOURCES <= m <= MAX_RESOURCES):
            self.set_status(
                f"Resource type count must be between {MIN_RESOURCES} and {MAX_RESOURCES}.",
                variant="danger",
            )
            return

        self.generate_matrix(n, m)
        self.set_status(f"Generated input tables for {n} customers and {m} resources.", variant="info")

    def generate_matrix(self, n: int, m: int) -> None:
        """
        Dynamically create Total vector, Maximum matrix, and Allocation matrix entries.

        Args:
            n: Number of customers (rows).
            m: Number of resources (columns).
        """
        self._current_n = n
        self._current_m = m

        # Clear existing widgets
        for widget in self.matrix_content.winfo_children():
            widget.destroy()

        self.total_entries.clear()
        self.maximum_entries.clear()
        self.allocation_entries.clear()

        # ---------------------------------------------------------------------
        # 1. Total System Resources Vector (1 x m)
        # ---------------------------------------------------------------------
        sec1_frame = tk.Frame(self.matrix_content, bg=BG_CARD)
        sec1_frame.pack(fill="x", pady=(0, PAD_LG))

        lbl_sec1 = tk.Label(
            sec1_frame,
            text="1. Total System Resources (Total Instances Available in System)",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_sec1.pack(anchor="w", pady=(0, PAD_SM))

        total_grid = tk.Frame(sec1_frame, bg=BG_CARD)
        total_grid.pack(anchor="w")

        for j in range(m):
            col_box = tk.Frame(total_grid, bg=BG_CARD)
            col_box.grid(row=0, column=j, padx=PAD_SM, pady=PAD_XS)

            lbl_rj = tk.Label(
                col_box,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=ACCENT_PRIMARY,
            )
            lbl_rj.pack()

            entry = self._create_cell_entry(col_box, default="0")
            entry.pack(pady=(2, 0))
            self.total_entries.append(entry)

        # ---------------------------------------------------------------------
        # 2. Maximum Claim Matrix (n x m)
        # ---------------------------------------------------------------------
        sec2_frame = tk.Frame(self.matrix_content, bg=BG_CARD)
        sec2_frame.pack(fill="x", pady=(0, PAD_LG))

        lbl_sec2 = tk.Label(
            sec2_frame,
            text="2. Maximum Matrix (Declared Maximum Resource Demand per Customer)",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_sec2.pack(anchor="w", pady=(0, PAD_SM))

        max_grid = tk.Frame(sec2_frame, bg=BG_CARD)
        max_grid.pack(anchor="w")

        # Column Headers
        lbl_corner = tk.Label(max_grid, text="Customer", font=FONT_CAPTION_BOLD, bg=BG_CARD, fg=TEXT_MUTED)
        lbl_corner.grid(row=0, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

        for j in range(m):
            lbl_col = tk.Label(
                max_grid,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                width=6,
            )
            lbl_col.grid(row=0, column=j + 1, padx=PAD_XS, pady=PAD_XS)

        # Matrix Rows
        for i in range(n):
            row_entries: List[tk.Entry] = []
            lbl_row = tk.Label(
                max_grid,
                text=f"C{i}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
            )
            lbl_row.grid(row=i + 1, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

            for j in range(m):
                entry = self._create_cell_entry(max_grid, default="0")
                entry.grid(row=i + 1, column=j + 1, padx=PAD_XS, pady=PAD_XS)
                row_entries.append(entry)
            self.maximum_entries.append(row_entries)

        # ---------------------------------------------------------------------
        # 3. Allocation Matrix (n x m)
        # ---------------------------------------------------------------------
        sec3_frame = tk.Frame(self.matrix_content, bg=BG_CARD)
        sec3_frame.pack(fill="x", pady=(0, PAD_SM))

        lbl_sec3 = tk.Label(
            sec3_frame,
            text="3. Allocation Matrix (Currently Allocated Resources per Customer)",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_sec3.pack(anchor="w", pady=(0, PAD_SM))

        alloc_grid = tk.Frame(sec3_frame, bg=BG_CARD)
        alloc_grid.pack(anchor="w")

        # Column Headers
        lbl_corner_alloc = tk.Label(
            alloc_grid, text="Customer", font=FONT_CAPTION_BOLD, bg=BG_CARD, fg=TEXT_MUTED
        )
        lbl_corner_alloc.grid(row=0, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

        for j in range(m):
            lbl_col = tk.Label(
                alloc_grid,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
                width=6,
            )
            lbl_col.grid(row=0, column=j + 1, padx=PAD_XS, pady=PAD_XS)

        # Matrix Rows
        for i in range(n):
            row_entries = []
            lbl_row = tk.Label(
                alloc_grid,
                text=f"C{i}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
            )
            lbl_row.grid(row=i + 1, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

            for j in range(m):
                entry = self._create_cell_entry(alloc_grid, default="0")
                entry.grid(row=i + 1, column=j + 1, padx=PAD_XS, pady=PAD_XS)
                row_entries.append(entry)
            self.allocation_entries.append(row_entries)

        # ---------------------------------------------------------------------
        # 4. Results Section (Calculated Need Matrix & Snapshot - Initially hidden)
        # ---------------------------------------------------------------------
        self.results_section_frame = tk.Frame(self.matrix_content, bg=BG_CARD)
        self.results_section_frame.pack_forget()

    def _create_cell_entry(self, parent: tk.Widget, default: str = "0") -> tk.Entry:
        """Create a styled, centered numeric matrix cell entry."""
        entry = tk.Entry(
            parent,
            width=6,
            font=FONT_MONO,
            justify="center",
            bg=BG_SIDEBAR,
            fg=TEXT_PRIMARY,
            insertbackground=TEXT_PRIMARY,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=ACCENT_PRIMARY,
        )
        entry.insert(0, default)

        # Focus outline feedback
        entry.bind(
            "<FocusIn>",
            lambda e=None, ent=entry: ent.configure(highlightbackground=ACCENT_PRIMARY),
        )
        entry.bind(
            "<FocusOut>",
            lambda e=None, ent=entry: ent.configure(highlightbackground=BORDER_COLOR),
        )
        return entry

    # =========================================================================
    # Presets & Form Clearing
    # =========================================================================

    def clear_form(self) -> None:
        """Reset all matrix and vector cells to zero."""
        self._hide_results()
        for ent in self.total_entries:
            ent.delete(0, tk.END)
            ent.insert(0, "0")

        for row in self.maximum_entries:
            for ent in row:
                ent.delete(0, tk.END)
                ent.insert(0, "0")

        for row in self.allocation_entries:
            for ent in row:
                ent.delete(0, tk.END)
                ent.insert(0, "0")

        self.clear_status()

    def load_preset(
        self,
        customers: int,
        resources: int,
        total: List[int],
        maximum: List[List[int]],
        allocation: List[List[int]],
    ) -> None:
        """Populate the configuration form with specified dimensions and matrix values."""
        self._hide_results()
        self.customers_var.set(str(customers))
        self.resources_var.set(str(resources))
        self.generate_matrix(customers, resources)

        # Fill Total
        for j, val in enumerate(total):
            if j < len(self.total_entries):
                self.total_entries[j].delete(0, tk.END)
                self.total_entries[j].insert(0, str(val))

        # Fill Maximum
        for i, row in enumerate(maximum):
            for j, val in enumerate(row):
                if i < len(self.maximum_entries) and j < len(self.maximum_entries[i]):
                    self.maximum_entries[i][j].delete(0, tk.END)
                    self.maximum_entries[i][j].insert(0, str(val))

        # Fill Allocation
        for i, row in enumerate(allocation):
            for j, val in enumerate(row):
                if i < len(self.allocation_entries) and j < len(self.allocation_entries[i]):
                    self.allocation_entries[i][j].delete(0, tk.END)
                    self.allocation_entries[i][j].insert(0, str(val))

        self.set_status(f"Loaded preset ({customers} customers, {resources} resources).", variant="info")

    def load_preset_5x3(self) -> None:
        """Load standard 5-customer, 3-resource dataset."""
        self.load_preset(
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

    def load_preset_3x2(self) -> None:
        """Load compact 3-customer, 2-resource dataset."""
        self.load_preset(
            customers=3,
            resources=2,
            total=[10, 10],
            maximum=[
                [7, 5],
                [3, 2],
                [5, 5],
            ],
            allocation=[
                [2, 1],
                [1, 1],
                [2, 0],
            ],
        )

    # =========================================================================
    # Validation & Data Collection
    # =========================================================================

    def validate_and_collect_data(
        self,
    ) -> Optional[Tuple[int, int, List[int], List[List[int]], List[List[int]]]]:
        """
        Validate all entries against protocol and algorithmic rules.

        Validation Rules:
        1. Dimension limits: customers 1-50, resources 1-10.
        2. All entries in Total, Maximum, and Allocation must be non-negative integers.
        3. Maximum entries must not exceed MAX_RESOURCE_CAPACITY (1000).
        4. Allocation per customer/resource cannot exceed Maximum claim: Alloc[i][j] <= Max[i][j].
        5. Total allocation across all customers cannot exceed Total instances: Sum(Alloc[*][j]) <= Total[j].

        Returns:
            Tuple of (customers, resources, total, maximum, allocation) or None if invalid.
        """
        self.clear_status()

        # 1. Dimension validation
        try:
            n = int(self.customers_var.get().strip())
        except ValueError:
            self.set_status("Customer count must be a valid integer.", variant="danger")
            return None

        if not (MIN_CUSTOMERS <= n <= MAX_CUSTOMERS):
            self.set_status(
                f"Customer count must be between {MIN_CUSTOMERS} and {MAX_CUSTOMERS}.",
                variant="danger",
            )
            return None

        try:
            m = int(self.resources_var.get().strip())
        except ValueError:
            self.set_status("Resource count must be a valid integer.", variant="danger")
            return None

        if not (MIN_RESOURCES <= m <= MAX_RESOURCES):
            self.set_status(
                f"Resource count must be between {MIN_RESOURCES} and {MAX_RESOURCES}.",
                variant="danger",
            )
            return None

        # Verify matrix entries exist and match dimensions
        if (
            len(self.total_entries) != m
            or len(self.maximum_entries) != n
            or len(self.allocation_entries) != n
        ):
            self.set_status(
                "Matrix dimensions do not match inputs. Please click 'Generate Matrix' first.",
                variant="danger",
            )
            return None

        # 2. Total Resources validation
        total: List[int] = []
        for j in range(m):
            raw = self.total_entries[j].get().strip()
            try:
                val = int(raw)
            except ValueError:
                self.set_status(f"Total instances for R{j} must be an integer.", variant="danger")
                return None
            if val < 0 or val > MAX_RESOURCE_CAPACITY:
                self.set_status(
                    f"Total instances for R{j} must be between 0 and {MAX_RESOURCE_CAPACITY}.",
                    variant="danger",
                )
                return None
            total.append(val)

        # 3. Maximum Matrix validation
        maximum: List[List[int]] = []
        for i in range(n):
            row: List[int] = []
            for j in range(m):
                raw = self.maximum_entries[i][j].get().strip()
                try:
                    val = int(raw)
                except ValueError:
                    self.set_status(
                        f"Maximum entry for Customer C{i}, Resource R{j} must be an integer.",
                        variant="danger",
                    )
                    return None
                if val < 0 or val > MAX_RESOURCE_CAPACITY:
                    self.set_status(
                        f"Maximum entry for Customer C{i}, Resource R{j} must be between 0 and {MAX_RESOURCE_CAPACITY}.",
                        variant="danger",
                    )
                    return None
                row.append(val)
            maximum.append(row)

        # 4. Allocation Matrix validation & Alloc <= Max check
        allocation: List[List[int]] = []
        for i in range(n):
            row = []
            for j in range(m):
                raw = self.allocation_entries[i][j].get().strip()
                try:
                    val = int(raw)
                except ValueError:
                    self.set_status(
                        f"Allocation entry for Customer C{i}, Resource R{j} must be an integer.",
                        variant="danger",
                    )
                    return None
                if val < 0:
                    self.set_status(
                        f"Allocation for Customer C{i}, Resource R{j} cannot be negative ({val}).",
                        variant="danger",
                    )
                    return None
                # Rule: Allocation <= Maximum
                if val > maximum[i][j]:
                    self.set_status(
                        f"Allocation for C{i}, R{j} ({val}) exceeds Maximum claim ({maximum[i][j]}).",
                        variant="danger",
                    )
                    return None
                row.append(val)
            allocation.append(row)

        # 5. Sum(Allocation) <= Total validation
        for j in range(m):
            alloc_sum = sum(allocation[i][j] for i in range(n))
            if alloc_sum > total[j]:
                self.set_status(
                    f"Total allocated instances for R{j} ({alloc_sum}) exceed Total existing instances ({total[j]}).",
                    variant="danger",
                )
                return None

        return n, m, total, maximum, allocation

    # =========================================================================
    # Backend Initialization Dispatch & Polling
    # =========================================================================

    def initialize_bank(self) -> None:
        """
        Validate form data and dispatch 'initialize' command to C backend.

        Guards against duplicate submissions while initialization is in progress.
        Uses non-blocking Tkinter after() polling to handle backend responses.
        """
        # Duplicate submission guard
        if self._init_pending:
            logger.warning("Initialize requested while another initialization is pending. Ignoring duplicate click.")
            return

        validated = self.validate_and_collect_data()
        if validated is None:
            return

        n, m, total, maximum, allocation = validated

        if not self.client.is_running():
            self.set_status("Cannot initialize: Backend process is not running.", variant="danger")
            return

        # Lock UI state to prevent duplicate submissions
        self._init_pending = True
        self._hide_results()
        self.btn_init.configure(state="disabled", text="Initializing...")
        self.btn_init.update_idletasks()
        self.set_status("Sending configuration to C backend...", variant="info")

        try:
            self.client.initialize(
                customers=n,
                resources=m,
                total=total,
                maximum=maximum,
                allocation=allocation,
            )
        except Exception as e:
            self._init_pending = False
            self.btn_init.configure(state="normal", text="Initialize Bank")
            self.set_status(f"Failed to transmit configuration: {e}", variant="danger")
            return

        # Start non-blocking polling for backend response
        self._poll_deadline = time.time() + 5.0
        self._poll_job = self.after(40, self._check_init_response)

    def _check_init_response(self) -> None:
        """Poll BackendClient response queue non-blockingly for initialize results."""
        if not self._init_pending or not self.winfo_exists():
            return

        # Drain messages until status or snapshot is found
        while True:
            msg = self.client.get_message(timeout=0)
            if msg is None:
                break

            status = msg.get("status")

            # 1. Error returned by backend
            if status == "error":
                self._init_pending = False
                self.btn_init.configure(state="normal", text="Initialize Bank")
                err_msg = msg.get("message", "Initialization rejected by backend")
                self.set_status(f"Backend rejected configuration: {err_msg}", variant="danger")
                self._hide_results()
                return

            # 2. Ack message {"status": "ok", "message": "Bank initialized"}
            if status == "ok" and msg.get("message") == "Bank initialized":
                # Wait for the snapshot line that follows immediately
                continue

            # 3. Snapshot message received
            if status == "ok" and "customers" in msg and "resources" in msg and "available" in msg:
                self._init_pending = False
                self.btn_init.configure(state="normal", text="Re-initialize Bank")
                self._last_snapshot = msg
                self._display_results(msg)

                # Notify parent application if callback registered
                if self.on_initialized:
                    try:
                        self.on_initialized(msg)
                    except Exception as err:
                        logger.error("Error in on_initialized callback: %s", err)
                return

        # Check for timeout
        if time.time() > self._poll_deadline:
            self._init_pending = False
            self.btn_init.configure(state="normal", text="Initialize Bank")
            self.set_status("Initialization timed out waiting for backend.", variant="danger")
            return

        # Reschedule check
        if self.winfo_exists() and self._init_pending:
            self._poll_job = self.after(40, self._check_init_response)

    # =========================================================================
    # Results Display & Navigation
    # =========================================================================

    def _display_results(self, snapshot: Dict[str, Any]) -> None:
        """
        Render real backend results (Available vector, Need matrix, Safety, Safe sequence).

        Displays both the top success banner and the detailed Section 4 inside the viewport.
        """
        customers = snapshot.get("customers", 0)
        resources = snapshot.get("resources", 0)
        available = snapshot.get("available", [])
        need = snapshot.get("need", [])
        is_safe = snapshot.get("safe", False)
        safe_seq = snapshot.get("safe_sequence", [])

        safe_str = "SAFE STATE" if is_safe else "UNSAFE STATE"
        seq_display = (
            " → ".join(f"C{c}" for c in safe_seq)
            if (is_safe and safe_seq)
            else "None (Potential Deadlock Hazard)"
        )
        avail_display = "[" + ", ".join(str(x) for x in available) + "]"

        # 1. Update top banner with rich summary
        details_msg = (
            f"Dimensions: {customers} Customers, {resources} Resources  |  "
            f"Available Pool: {avail_display}  |  "
            f"Status: {safe_str}  |  "
            f"Safe Sequence: {seq_display}"
        )
        self.set_status(
            f"Bank initialized successfully! State: {safe_str}",
            variant="success" if is_safe else "warning",
            details=details_msg,
            show_dashboard_btn=True,
        )

        # 2. Show Go to Dashboard in bottom action bar
        self.btn_action_dashboard.pack(side="left", padx=(0, PAD_MD), before=self.lbl_init_hint)

        # 3. Build Section 4 inside scrollable content
        for w in self.results_section_frame.winfo_children():
            w.destroy()

        self.results_section_frame.pack(fill="x", pady=(PAD_LG, 0))

        # Title
        lbl_sec4 = tk.Label(
            self.results_section_frame,
            text="4. Calculated Need Matrix & System Safety (C Backend Output)",
            font=FONT_SECTION,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
        )
        lbl_sec4.pack(anchor="w", pady=(0, PAD_SM))

        # KPI row for Results
        kpi_row = tk.Frame(self.results_section_frame, bg=BG_CARD)
        kpi_row.pack(fill="x", pady=(0, PAD_MD))

        # Safety pill
        badge_safety = create_badge(
            kpi_row,
            text=f"● {safe_str}",
            variant="success" if is_safe else "danger",
            font=FONT_BODY_BOLD,
        )
        badge_safety.pack(side="left", padx=(0, PAD_MD))

        # Safe sequence label
        lbl_seq = tk.Label(
            kpi_row,
            text=f"Safe Sequence: {seq_display}",
            font=FONT_MONO_BOLD if is_safe else FONT_BODY_BOLD,
            bg=BG_CARD,
            fg="#86EFAC" if is_safe else "#FCA5A5",
        )
        lbl_seq.pack(side="left", padx=(0, PAD_MD))

        # Available pool label
        lbl_avail = tk.Label(
            kpi_row,
            text=f"Available: {avail_display}",
            font=FONT_MONO_BOLD,
            bg=BG_CARD,
            fg=ACCENT_INFO,
        )
        lbl_avail.pack(side="left", padx=(0, PAD_MD))

        # Need Matrix Table
        need_grid = tk.Frame(self.results_section_frame, bg=BG_CARD)
        need_grid.pack(anchor="w", pady=(PAD_XS, PAD_MD))

        lbl_corner_need = tk.Label(
            need_grid,
            text="Customer",
            font=FONT_CAPTION_BOLD,
            bg=BG_CARD,
            fg=TEXT_MUTED,
        )
        lbl_corner_need.grid(row=0, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

        for j in range(resources):
            lbl_col = tk.Label(
                need_grid,
                text=f"R{j}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=ACCENT_PRIMARY,
                width=6,
            )
            lbl_col.grid(row=0, column=j + 1, padx=PAD_XS, pady=PAD_XS)

        for i in range(customers):
            lbl_row = tk.Label(
                need_grid,
                text=f"C{i}",
                font=FONT_CARD_TITLE,
                bg=BG_CARD,
                fg=TEXT_SECONDARY,
            )
            lbl_row.grid(row=i + 1, column=0, padx=PAD_MD, pady=PAD_XS, sticky="w")

            row_need = need[i] if i < len(need) else []
            for j in range(resources):
                val = row_need[j] if j < len(row_need) else 0
                lbl_cell = tk.Label(
                    need_grid,
                    text=str(val),
                    font=FONT_MONO_BOLD,
                    width=6,
                    bg=BG_SIDEBAR,
                    fg=TEXT_PRIMARY,
                    highlightthickness=1,
                    highlightbackground=BORDER_COLOR,
                    pady=2,
                )
                lbl_cell.grid(row=i + 1, column=j + 1, padx=PAD_XS, pady=PAD_XS)

        # Section 4 action row: Go to Dashboard button
        res_actions = tk.Frame(self.results_section_frame, bg=BG_CARD)
        res_actions.pack(fill="x", pady=(PAD_SM, 0))

        btn_go_res = ttk.Button(
            res_actions,
            text="Go to Dashboard →",
            style="Success.TButton",
            command=self.go_to_dashboard,
        )
        btn_go_res.pack(side="left")

        # Scroll viewport so Section 4 results are immediately visible
        self.after(60, lambda: self.canvas.yview_moveto(1.0))

    def _hide_results(self) -> None:
        """Hide the calculated results section and dashboard navigation buttons."""
        if hasattr(self, "results_section_frame"):
            self.results_section_frame.pack_forget()
        if hasattr(self, "btn_action_dashboard"):
            self.btn_action_dashboard.pack_forget()
        if hasattr(self, "btn_banner_dashboard"):
            self.btn_banner_dashboard.pack_forget()

    def go_to_dashboard(self) -> None:
        """Trigger navigation callback to return to or refresh the main dashboard."""
        if not self._last_snapshot:
            self.set_status(
                "Please initialize the bank successfully before proceeding to the Dashboard.",
                variant="warning",
            )
            return

        callback = self.on_navigate_dashboard or self.on_go_to_dashboard
        if callback:
            try:
                callback()
                return
            except Exception as e:
                logger.error("Error in on_navigate_dashboard callback: %s", e)

        if self.on_initialized and self._last_snapshot:
            try:
                self.on_initialized(self._last_snapshot)
            except Exception as e:
                logger.error("Error in on_initialized callback: %s", e)

    def is_pending(self) -> bool:
        """Return True if an initialization request is currently awaiting backend response."""
        return self._init_pending

    def destroy(self) -> None:
        """Cleanly cancel any pending timer before destroying widget."""
        self._init_pending = False
        if hasattr(self, "_poll_job") and self._poll_job:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        super().destroy()


# =============================================================================
# Standalone Launcher
# =============================================================================
def main() -> None:
    """Run ConfigurationFrame directly in a test window."""
    root = tk.Tk()
    root.title("Banker's Algorithm — Dynamic Configuration")
    root.geometry("1024x720")
    root.minsize(850, 550)

    setup_styles(root)

    client = BackendClient()
    try:
        client.start()
        print(f"Backend active (PID: {client._process.pid if client._process else '?'})")
    except Exception as e:
        print(f"Backend startup warning: {e}")

    def on_init(snapshot: Dict[str, Any]) -> None:
        print(
            f"Successfully initialized: {snapshot.get('customers')} customers, "
            f"Safe={snapshot.get('safe')}, Sequence={snapshot.get('safe_sequence')}"
        )

    def on_dashboard() -> None:
        print("Navigating to Dashboard! Callback triggered.")

    config_frame = ConfigurationFrame(
        root,
        client=client,
        on_initialized=on_init,
        on_go_to_dashboard=on_dashboard,
    )
    config_frame.pack(fill="both", expand=True)

    def on_close() -> None:
        if client.is_running():
            client.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
