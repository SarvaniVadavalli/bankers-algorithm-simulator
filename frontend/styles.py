"""
styles.py: Reusable styling, themes, fonts, colors, and ttk styles
for the Banker's Algorithm Resource Management Simulator frontend.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Tuple

# =============================================================================
# Color Palette
# =============================================================================
# Core theme requirements
BG_MAIN: str = "#111827"  # Deep dark gray/black background
BG_SIDEBAR: str = "#0B1220"  # Very dark slate sidebar
BG_CARD: str = "#1F2937"  # Card background
BG_CARD_ALT: str = "#182234"  # Subtle alternative card surface
BG_CARD_HOVER: str = "#263445"  # Card hover / active surface

# Borders and separators
BORDER_COLOR: str = "#374151"  # Subtle dark border
BORDER_LIGHT: str = "#4B5563"  # Slightly lighter border
BORDER_SUBTLE: str = "#222D3D"  # Very subtle divider

# Accents
ACCENT_PRIMARY: str = "#3B82F6"  # Blue
ACCENT_PRIMARY_HOVER: str = "#2563EB"  # Darker blue
ACCENT_PRIMARY_BG: str = "#1E3A8A"  # Soft blue background for badges

ACCENT_SUCCESS: str = "#22C55E"  # Emerald green
ACCENT_SUCCESS_HOVER: str = "#16A34A"  # Darker green
ACCENT_SUCCESS_BG: str = "#064E3B"  # Soft green background for badges

ACCENT_WARNING: str = "#F59E0B"  # Amber
ACCENT_WARNING_HOVER: str = "#D97706"  # Darker amber
ACCENT_WARNING_BG: str = "#78350F"  # Soft amber background for badges

ACCENT_DANGER: str = "#EF4444"  # Rose red
ACCENT_DANGER_HOVER: str = "#DC2626"  # Darker red
ACCENT_DANGER_BG: str = "#7F1D1D"  # Soft red background for badges

ACCENT_INFO: str = "#38BDF8"  # Light sky blue
ACCENT_PURPLE: str = "#A855F7"  # Purple

# Typography colors
TEXT_PRIMARY: str = "#F9FAFB"  # Bright white / light gray
TEXT_SECONDARY: str = "#9CA3AF"  # Medium gray
TEXT_MUTED: str = "#6B7280"  # Muted gray
TEXT_INVERSE: str = "#111827"  # Inverted dark text for bright pills

# Activity log badges
LOG_COLORS = {
    "INIT": (ACCENT_PRIMARY_BG, "#93C5FD"),
    "SNAPSHOT": ("#374151", "#E5E7EB"),
    "GRANTED": (ACCENT_SUCCESS_BG, "#86EFAC"),
    "UNSAFE": (ACCENT_WARNING_BG, "#FDE047"),
    "UNAVAIL": (ACCENT_WARNING_BG, "#FDE047"),
    "EXCEEDS": (ACCENT_DANGER_BG, "#FCA5A5"),
    "RELEASE": (ACCENT_PRIMARY_BG, "#93C5FD"),
    "AUTO": ("#312E81", "#C7D2FE"),
    "COMPLETE": (ACCENT_SUCCESS_BG, "#86EFAC"),
    "RESET": ("#4B5563", "#F3F4F6"),
    "ERROR": (ACCENT_DANGER_BG, "#FCA5A5"),
}

# =============================================================================
# Spacing Constants
# =============================================================================
PAD_XS: int = 4
PAD_SM: int = 8
PAD_MD: int = 12
PAD_LG: int = 16
PAD_XL: int = 20
PAD_2XL: int = 24

# =============================================================================
# Typography
# =============================================================================
# Platform-aware font family resolution
if sys.platform == "win32":
    FONT_FAMILY = "Segoe UI"
    FONT_MONO_FAMILY = "Consolas"
elif sys.platform == "darwin":
    FONT_FAMILY = "SF Pro Text"
    FONT_MONO_FAMILY = "SF Mono"
else:
    FONT_FAMILY = "DejaVu Sans"
    FONT_MONO_FAMILY = "DejaVu Sans Mono"

# Font definitions: (family, size, weight)
FONT_TITLE: Tuple[str, int, str] = (FONT_FAMILY, 15, "bold")
FONT_SUBTITLE: Tuple[str, int, str] = (FONT_FAMILY, 10, "normal")
FONT_SECTION: Tuple[str, int, str] = (FONT_FAMILY, 12, "bold")
FONT_SUBSECTION: Tuple[str, int, str] = (FONT_FAMILY, 11, "bold")

FONT_CARD_TITLE: Tuple[str, int, str] = (FONT_FAMILY, 9, "bold")
FONT_STAT_LARGE: Tuple[str, int, str] = (FONT_FAMILY, 20, "bold")
FONT_STAT_MED: Tuple[str, int, str] = (FONT_FAMILY, 14, "bold")
FONT_STAT_SUB: Tuple[str, int, str] = (FONT_FAMILY, 9, "normal")

FONT_BODY: Tuple[str, int, str] = (FONT_FAMILY, 10, "normal")
FONT_BODY_BOLD: Tuple[str, int, str] = (FONT_FAMILY, 10, "bold")
FONT_CAPTION: Tuple[str, int, str] = (FONT_FAMILY, 9, "normal")
FONT_CAPTION_BOLD: Tuple[str, int, str] = (FONT_FAMILY, 9, "bold")

FONT_MONO: Tuple[str, int, str] = (FONT_MONO_FAMILY, 9, "normal")
FONT_MONO_BOLD: Tuple[str, int, str] = (FONT_MONO_FAMILY, 9, "bold")
FONT_MONO_SM: Tuple[str, int, str] = (FONT_MONO_FAMILY, 8, "normal")


# =============================================================================
# Theme Configuration
# =============================================================================
def setup_styles(root: tk.Tk) -> ttk.Style:
    """
    Apply professional dark theme settings across standard Tk and ttk widgets.

    Args:
        root: The Tk root window.

    Returns:
        The configured ttk.Style instance.
    """
    root.configure(bg=BG_MAIN)

    style = ttk.Style(root)

    # Use clam theme as the base for robust dark mode styling across platforms
    available_themes = style.theme_names()
    if "clam" in available_themes:
        style.theme_use("clam")

    # Base Frame styling
    style.configure(
        "TFrame",
        background=BG_MAIN,
    )
    style.configure(
        "Card.TFrame",
        background=BG_CARD,
    )
    style.configure(
        "Sidebar.TFrame",
        background=BG_SIDEBAR,
    )

    # Base Label styling
    style.configure(
        "TLabel",
        background=BG_MAIN,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
    )
    style.configure(
        "Card.TLabel",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
    )
    style.configure(
        "CardTitle.TLabel",
        background=BG_CARD,
        foreground=TEXT_SECONDARY,
        font=FONT_CARD_TITLE,
    )
    style.configure(
        "CardStat.TLabel",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        font=FONT_STAT_LARGE,
    )
    style.configure(
        "CardSub.TLabel",
        background=BG_CARD,
        foreground=TEXT_MUTED,
        font=FONT_STAT_SUB,
    )

    style.configure(
        "Header.TLabel",
        background=BG_MAIN,
        foreground=TEXT_PRIMARY,
        font=FONT_TITLE,
    )
    style.configure(
        "Subheader.TLabel",
        background=BG_MAIN,
        foreground=TEXT_SECONDARY,
        font=FONT_SUBTITLE,
    )
    style.configure(
        "Section.TLabel",
        background=BG_MAIN,
        foreground=TEXT_PRIMARY,
        font=FONT_SECTION,
    )
    style.configure(
        "Muted.TLabel",
        background=BG_MAIN,
        foreground=TEXT_MUTED,
        font=FONT_CAPTION,
    )

    # Primary Action Button
    style.configure(
        "Primary.TButton",
        background=ACCENT_PRIMARY,
        foreground="#FFFFFF",
        font=FONT_BODY_BOLD,
        borderwidth=0,
        focusthickness=0,
        focuscolor="none",
        padding=(PAD_MD, PAD_SM),
    )
    style.map(
        "Primary.TButton",
        background=[("active", ACCENT_PRIMARY_HOVER), ("disabled", BORDER_COLOR)],
        foreground=[("disabled", TEXT_MUTED)],
    )

    # Secondary / Outline Button
    style.configure(
        "Secondary.TButton",
        background=BORDER_COLOR,
        foreground=TEXT_PRIMARY,
        font=FONT_BODY,
        borderwidth=0,
        focusthickness=0,
        focuscolor="none",
        padding=(PAD_MD, PAD_SM),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", BORDER_LIGHT), ("disabled", BG_CARD)],
        foreground=[("disabled", TEXT_MUTED)],
    )

    # Success Action Button
    style.configure(
        "Success.TButton",
        background=ACCENT_SUCCESS,
        foreground="#FFFFFF",
        font=FONT_BODY_BOLD,
        borderwidth=0,
        focusthickness=0,
        focuscolor="none",
        padding=(PAD_MD, PAD_SM),
    )
    style.map(
        "Success.TButton",
        background=[("active", ACCENT_SUCCESS_HOVER), ("disabled", BORDER_COLOR)],
        foreground=[("disabled", TEXT_MUTED)],
    )

    # Treeview (for tabular data)
    style.configure(
        "Treeview",
        background=BG_CARD,
        foreground=TEXT_PRIMARY,
        fieldbackground=BG_CARD,
        borderwidth=0,
        font=FONT_MONO,
        rowheight=26,
    )
    style.configure(
        "Treeview.Heading",
        background=BG_SIDEBAR,
        foreground=TEXT_SECONDARY,
        font=FONT_CARD_TITLE,
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", BG_CARD_HOVER)],
        foreground=[("selected", TEXT_PRIMARY)],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", BG_CARD)],
    )

    # Scrollbars
    style.configure(
        "Vertical.TScrollbar",
        background=BG_CARD,
        troughcolor=BG_MAIN,
        bordercolor=BG_MAIN,
        arrowcolor=TEXT_SECONDARY,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", BORDER_LIGHT), ("disabled", BG_MAIN)],
    )

    # Progressbar
    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT_PRIMARY,
        troughcolor=BORDER_COLOR,
        borderwidth=0,
        thickness=8,
    )

    # Separator
    style.configure(
        "TSeparator",
        background=BORDER_COLOR,
    )

    return style


# =============================================================================
# Reusable Card Container Helper
# =============================================================================
def create_card(
    parent: tk.Widget,
    bg: str = BG_CARD,
    border_color: str = BORDER_COLOR,
    border_width: int = 1,
    padx: int = PAD_LG,
    pady: int = PAD_LG,
    **kwargs,
) -> tk.Frame:
    """
    Create a polished card container with crisp borders and uniform dark padding.

    Args:
        parent: The master widget.
        bg: Background color of the card.
        border_color: Outline border color.
        border_width: Border line width (defaults to 1px).
        padx: Internal horizontal padding.
        pady: Internal vertical padding.

    Returns:
        A styled tk.Frame ready for child widgets.
    """
    card = tk.Frame(
        parent,
        bg=bg,
        highlightbackground=border_color,
        highlightcolor=border_color,
        highlightthickness=border_width,
        bd=0,
        padx=padx,
        pady=pady,
        **kwargs,
    )
    return card


# =============================================================================
# Status Badge Pill Widget
# =============================================================================
def create_badge(
    parent: tk.Widget,
    text: str,
    variant: str = "neutral",
    font: Tuple[str, int, str] = FONT_CAPTION_BOLD,
) -> tk.Label:
    """
    Create a pill badge label with appropriate background and text contrast.

    Variants: 'success', 'warning', 'danger', 'primary', 'neutral'
    """
    styles_map = {
        "success": (ACCENT_SUCCESS_BG, "#86EFAC"),
        "warning": (ACCENT_WARNING_BG, "#FDE047"),
        "danger": (ACCENT_DANGER_BG, "#FCA5A5"),
        "primary": (ACCENT_PRIMARY_BG, "#93C5FD"),
        "neutral": ("#374151", "#E5E7EB"),
    }
    bg, fg = styles_map.get(variant, styles_map["neutral"])

    badge = tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=font,
        padx=PAD_SM,
        pady=2,
    )
    return badge

