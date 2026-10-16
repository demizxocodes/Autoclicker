"""Dark theme for the ttk widgets, the classic Tk dialogs, and the Windows title bar."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

BG = "#1e1f22"
SURFACE = "#2b2d31"
FIELD = "#313338"
BORDER = "#43454b"
TEXT = "#e8e9eb"
MUTED = "#9a9ca3"
DISABLED = "#6d6f76"
SELECT = "#2d4a7a"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2f6fdc"
STOP = "#dc2626"
STOP_HOVER = "#b91c1c"

FONT = ("Segoe UI", 10)
BOLD = ("Segoe UI", 10, "bold")
BIG = ("Segoe UI", 12, "bold")


def apply_dark_theme(root: tk.Tk) -> None:
    root.configure(bg=BG)

    # Classic Tk widgets: the profile-name dialog and the combobox drop-down lists.
    for pattern, value in (
        ("*Background", BG),
        ("*Foreground", TEXT),
        ("*activeBackground", BORDER),
        ("*activeForeground", TEXT),
        ("*selectBackground", SELECT),
        ("*selectForeground", TEXT),
        ("*highlightBackground", BG),
        ("*Entry.Background", FIELD),
        ("*Entry.insertBackground", TEXT),
        ("*Button.Background", SURFACE),
        ("*TCombobox*Listbox.background", FIELD),
        ("*TCombobox*Listbox.foreground", TEXT),
        ("*TCombobox*Listbox.selectBackground", SELECT),
        ("*TCombobox*Listbox.selectForeground", TEXT),
    ):
        root.option_add(pattern, value)

    style = ttk.Style(root)
    style.theme_use("clam")  # the built-in theme whose colors can all be changed

    style.configure(
        ".",
        background=BG, foreground=TEXT, fieldbackground=FIELD, font=FONT,
        bordercolor=BORDER, darkcolor=SURFACE, lightcolor=SURFACE, troughcolor=SURFACE,
        focuscolor=ACCENT, selectbackground=SELECT, selectforeground=TEXT,
        insertcolor=TEXT, arrowcolor=TEXT,
    )
    style.map(".", foreground=[("disabled", DISABLED)])

    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=TEXT, font=BOLD)

    style.configure("TButton", background=SURFACE, padding=(10, 4), relief="flat")
    style.map(
        "TButton",
        background=[("disabled", BG), ("pressed", FIELD), ("active", BORDER)],
        bordercolor=[("focus", ACCENT)],
    )
    for name, color, hover in (("Accent.TButton", ACCENT, ACCENT_HOVER), ("Stop.TButton", STOP, STOP_HOVER)):
        style.configure(name, background=color, foreground="white", font=BIG, padding=8, bordercolor=color)
        style.map(name, background=[("pressed", hover), ("active", hover)], bordercolor=[("focus", "white")])

    for name in ("TEntry", "TSpinbox", "TCombobox"):
        style.configure(name, fieldbackground=FIELD, background=SURFACE, foreground=TEXT, arrowcolor=TEXT,
                        insertcolor=TEXT, padding=3)
        style.map(
            name,
            fieldbackground=[("disabled", BG), ("readonly", FIELD)],
            foreground=[("disabled", DISABLED)],
            bordercolor=[("focus", ACCENT)],
            # Keep the read-only combobox text from looking permanently highlighted.
            selectbackground=[("readonly", FIELD)],
            selectforeground=[("readonly", TEXT)],
        )

    style.configure("TRadiobutton", background=BG, indicatorbackground=FIELD, indicatorforeground="white",
                    upperbordercolor=BORDER, lowerbordercolor=BORDER)
    style.map(
        "TRadiobutton",
        background=[("active", BG)],
        indicatorbackground=[("selected", ACCENT), ("active", BORDER)],
    )

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT,
                    rowheight=26, bordercolor=BORDER)
    style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", background=FIELD, foreground=TEXT, font=BOLD, relief="flat")
    style.map("Treeview.Heading", background=[("active", BORDER)])


def dark_title_bar(window: tk.Misc) -> None:
    """Ask Windows 10/11 to draw this window's title bar dark."""
    if sys.platform != "win32":
        return
    import ctypes

    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    value = ctypes.c_int(1)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, then older builds)
        if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
            break
