from __future__ import annotations

import csv
import io
import json
import os
import queue
import threading
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..core import (
    EtsGroupAddress,
    EtsProjectPasswordRequired,
    GpaDatapoint,
    SyncCandidate,
    SyncStatus,
    build_partial_candidates,
    build_sync_candidates,
    export_candidates_csv,
    parse_ets_ga_export,
    parse_gpa_datapoints,
    write_updated_gpa,
)
from .. import __version__
from ..config import LICENSING_ENABLED
from ..licensing import (
    LicenseManager, LicenseStatus, LicenseStorage, TrialManager,
    NullProvider, get_machine_id,
)
from ..log import get_logger
from .fonts import get_fonts, TTK_BODY, TTK_BODY_BOLD, TTK_SMALL

_log = get_logger("gui.app")

# ── Akzentfarben (identisch mit Legacy) ───────────────────────────────────────
ACCENT      = "#42a51b"
ACCENT_DARK = "#2f8612"

# ── Externe Links ─────────────────────────────────────────────────────────────
_LICENSE_URL = "https://github.com/EugHel/ets-gpa-sync"

# ── Theme-Farbpalette ──────────────────────────────────────────────────────────
_PALETTE: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg":           "#1c1c1c",
        "panel":        "#2b2b2b",
        "panel2":       "#333333",
        "border":       "#3d3d3d",
        "text":         "#e8e8e8",
        "muted":        "#8a8a8a",
        "soft_green":   "#1e3b1e",
        "row_even":     "#2b2b2b",
        "row_odd":      "#313131",
        "tree_sel":     "#1e3b1e",
        "tree_sel_fg":  "#e8e8e8",
        "entry_bg":     "#363636",
        "toolbar_bg":   "#242424",
        "info_bg":      "#1c2a3a",
        "info_fg":      "#90b8e0",
        "info_border":  "#2a4a6a",
        "ambiguous_fg": "#a78bfa",
        "progress_bg":  "#3d3d3d",
    },
    "light": {
        "bg":           "#f6f8fb",
        "panel":        "#ffffff",
        "panel2":       "#f8fafc",
        "border":       "#d9dee8",
        "text":         "#172033",
        "muted":        "#667085",
        "soft_green":   "#eef9e8",
        "row_even":     "#ffffff",
        "row_odd":      "#fbfcfe",
        "tree_sel":     "#eef9e8",
        "tree_sel_fg":  "#111111",
        "entry_bg":     "#ffffff",
        "toolbar_bg":   "#f0f2f5",
        "info_bg":      "#eff6ff",
        "info_fg":      "#1e3a8a",
        "info_border":  "#bfdbfe",
        "ambiguous_fg": "#7c3aed",
        "progress_bg":  "#e0e0e0",
    },
}

# ── Config-Persistenz ──────────────────────────────────────────────────────────
_CONFIG_PATH = Path(os.getenv("APPDATA", str(Path.home()))) / "GPA-GA-Sync" / "config.json"


def _load_config() -> Dict[str, str]:
    try:
        return json.loads(_CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {"theme": "dark"}


def _save_config(cfg: Dict[str, str]) -> None:
    try:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    except Exception:
        pass


class _Tooltip:
    """Zeigt einen Hilfetext nach kurzem Hover über einem Widget."""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 700) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._job: Optional[str] = None
        self._win: Optional[tk.Toplevel] = None
        widget.bind("<Enter>",       self._on_enter,  add="+")
        widget.bind("<Leave>",       self._on_leave,  add="+")
        widget.bind("<ButtonPress>", self._on_leave,  add="+")

    def _on_enter(self, _=None) -> None:
        self._cancel()
        self._job = self._widget.after(self._delay, self._show)

    def _on_leave(self, _=None) -> None:
        self._cancel()
        self._hide()

    def _cancel(self) -> None:
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        if self._win:
            return
        x = self._widget.winfo_rootx() + 12
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._win = tk.Toplevel(self._widget)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x}+{y}")
        self._win.wm_attributes("-topmost", True)
        tk.Label(
            self._win, text=self._text,
            background="#2c2c2e", foreground="#f0f0f0",
            relief="flat", padx=10, pady=6,
            font=TTK_BODY, justify="left", wraplength=300,
        ).pack()

    def _hide(self) -> None:
        if self._win:
            self._win.destroy()
            self._win = None


def _shorten_path(path: str, max_len: int = 72) -> str:
    if not path:
        return "Noch keine Datei ausgewählt."
    if len(path) <= max_len:
        return path
    p = Path(path)
    return f".../{p.parent.name}/{p.name}"


def run_gui() -> None:
    # ── TkinterDnD + CustomTkinter Integration ─────────────────────────────────
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD

        class _DndCTk(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.TkdndVersion = TkinterDnD._require(self)

        BaseCTk = _DndCTk
        DND_AVAILABLE = True
    except Exception:
        BaseCTk = ctk.CTk
        DND_AVAILABLE = False
        DND_FILES = None

    cfg = _load_config()
    _initial_theme = cfg.get("theme", "dark")
    ctk.set_appearance_mode(_initial_theme)
    ctk.set_default_color_theme("green")

    # ── Hauptanwendung ─────────────────────────────────────────────────────────
    class App(BaseCTk):
        def __init__(self) -> None:
            super().__init__()
            # Zentrale Schrift-Stufen – direkt nach Tk-Init erstellen.
            # CTkFont skaliert automatisch mit Windows-DPI (kein manueller Eingriff).
            self._fonts = get_fonts()
            self.title("ETS GPA GA-Sync")
            self.geometry("1420x820")
            self.minsize(980, 560)

            self._theme_mode: str = _initial_theme

            self.gpa_var = tk.StringVar()
            self.ets_var = tk.StringVar()
            self.pwd_var = tk.StringVar()
            self.filter_var = tk.StringVar()
            self.status_var = tk.StringVar(
                value="Bereit. GPA-Projekt und/oder ETS-XML auswählen, dann analysieren."
            )
            self.detail_vars = {
                "status": tk.StringVar(value="-"),
                "ga":     tk.StringVar(value="-"),
                "source": tk.StringVar(value="-"),
                "old":    tk.StringVar(value="-"),
                "new":    tk.StringVar(value="-"),
            }
            self.kpi_vars = {
                "gpa":      tk.StringVar(value="–"),
                "ets":      tk.StringVar(value="–"),
                "diff":     tk.StringVar(value="0"),
                "selected": tk.StringVar(value="0"),
            }
            self.candidates: List[SyncCandidate] = []
            self.datapoint_name_by_path: Dict[str, str] = {}
            self.visible_iids: List[str] = []
            self._edit_entry: Optional[tk.Entry] = None
            self.sort_column: Optional[str] = None
            self.sort_reverse = False
            self.heading_titles = {
                "#0":    "Sync",
                "status":"Status",
                "ga":    "GA",
                "old":   "Aktueller GPA-Name",
                "new":   "Neuer GPA-Name",
            }

            if LICENSING_ENABLED:
                self._license_manager = self._init_licensing()

            self._try_set_app_icon()
            self._build_ui()
            self._apply_tree_style()
            self._setup_drop_targets()
            self._register_tooltips()
            if LICENSING_ENABLED:
                self._update_license_ui()

        @property
        def _p(self) -> Dict[str, str]:
            return _PALETTE[self._theme_mode]

        # ── Theme ──────────────────────────────────────────────────────────────

        def _toggle_theme(self) -> None:
            self._theme_mode = "light" if self._theme_mode == "dark" else "dark"
            ctk.set_appearance_mode(self._theme_mode)
            _save_config({"theme": self._theme_mode})
            self._apply_tree_style()
            self._refresh_legacy_widgets()

        def _apply_tree_style(self) -> None:
            p = self._p
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure("Treeview",
                            rowheight=32,
                            font=TTK_BODY,
                            background=p["row_even"],
                            fieldbackground=p["row_even"],
                            foreground=p["text"],
                            bordercolor=p["border"],
                            borderwidth=0)
            _sep_color = p["border"]
            style.configure("Treeview.Heading",
                            font=TTK_BODY_BOLD,
                            background=p["panel2"],
                            foreground=p["text"],
                            padding=(10, 9),
                            relief="groove",
                            bordercolor=_sep_color,
                            lightcolor=_sep_color,
                            darkcolor=_sep_color)
            style.map("Treeview",
                      background=[("selected", p["tree_sel"])],
                      foreground=[("selected", p["tree_sel_fg"])])
            _heading_hover = "#3d3d3d" if self._theme_mode == "dark" else "#e2e6ec"
            style.map("Treeview.Heading",
                      background=[("active", _heading_hover)],
                      foreground=[("active", p["text"])],
                      relief=[("active", "flat")])
            # Entfernt das "Treeview.field"-Element aus dem clam-Theme, das einen weißen Außenrahmen erzeugt.
            style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
            style.configure("Sync.Horizontal.TProgressbar",
                            troughcolor=p["progress_bg"],
                            background=ACCENT)
            if hasattr(self, "tree"):
                self.tree.tag_configure("even",          background=p["row_even"])
                self.tree.tag_configure("odd",           background=p["row_odd"])
                self.tree.tag_configure("selected_sync", background=p["soft_green"])
                self.tree.tag_configure("unselected_sync", foreground=p["muted"])
                self.tree.tag_configure("ambiguous",     foreground=p["ambiguous_fg"])

        def _refresh_legacy_widgets(self) -> None:
            """Aktualisiert tk/ttk-Widgets (kein Auto-Recolor bei CTK-Theme-Wechsel)."""
            p = self._p
            if hasattr(self, "_footer_frame"):
                self._footer_frame.configure(bg=p["bg"])
            if hasattr(self, "_status_label"):
                self._status_label.configure(bg=p["bg"], fg=p["text"])
            if hasattr(self, "_hint_label"):
                self._hint_label.configure(bg=p["bg"], fg=p["muted"])
            if hasattr(self, "_version_label"):
                self._version_label.configure(bg=p["bg"], fg=p["muted"])
            if hasattr(self, "tree_menu"):
                self.tree_menu.configure(bg=p["panel"], fg=p["text"],
                                         activebackground=p["soft_green"],
                                         activeforeground=p["text"])
            if hasattr(self, "_info_frame"):
                self._info_frame.configure(bg=p["info_bg"],
                                           highlightbackground=p["info_border"])
            if hasattr(self, "_info_label"):
                self._info_label.configure(bg=p["info_bg"], fg=p["info_fg"])
            if hasattr(self, "_logo_canvas") and self._logo_canvas is not None:
                self._logo_canvas.configure(bg=p["toolbar_bg"])
            if hasattr(self, "_kpi_canvases"):
                _kpi_bg = "gray86" if self._theme_mode == "light" else "gray17"
                for canvas in self._kpi_canvases:
                    canvas.configure(bg=_kpi_bg)
            if hasattr(self, "progress_bar"):
                self.progress_bar.configure(style="Sync.Horizontal.TProgressbar")

        # ── Icon ───────────────────────────────────────────────────────────────

        def _round_rect_canvas(self, canvas: tk.Canvas,
                               x1: int, y1: int, x2: int, y2: int, r: int, **kwargs) -> None:
            points = [x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
                      x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
                      x1, y2, x1, y2-r, x1, y1+r, x1, y1]
            canvas.create_polygon(points, smooth=True, **kwargs)

        def _make_gpa_kpi_icon(self, parent) -> tk.Canvas:
            _bg = "gray86" if self._theme_mode == "light" else "gray17"
            canvas = tk.Canvas(parent, width=44, height=44,
                               bg=_bg, highlightthickness=0, bd=0)
            self._round_rect_canvas(canvas, 2, 2, 42, 42, 9,
                                    fill="#f3f4f6", outline="#d1d5db", width=1)
            canvas.create_text(22, 10, text="GIRA", fill="#4b5563",
                               font=("Segoe UI", 7, "bold"))
            canvas.create_line(12, 28, 22, 18, 32, 28, fill="#4b5563", width=3)
            canvas.create_line(15, 27, 15, 35, 29, 35, 29, 27, fill="#4b5563", width=3)
            return canvas

        def _make_ets_kpi_icon(self, parent) -> tk.Canvas:
            _bg = "gray86" if self._theme_mode == "light" else "gray17"
            canvas = tk.Canvas(parent, width=44, height=44,
                               bg=_bg, highlightthickness=0, bd=0)
            canvas.create_rectangle(4, 4, 40, 40, fill="#2f9637", outline="#2f9637")
            canvas.create_line(8, 11, 22, 11, fill="white", width=3)
            canvas.create_line(8, 15, 18, 15, fill="white", width=2)
            canvas.create_rectangle(10, 25, 24, 38, outline="white", width=2)
            canvas.create_rectangle(26, 18, 38, 38, outline="white", width=2)
            for x in (13, 19):
                for y in (28, 34):
                    canvas.create_rectangle(x, y, x + 3, y + 3, fill="white", outline="white")
            for y in (22, 28, 34):
                canvas.create_line(30, y, 36, y, fill="white", width=2)
            return canvas

        def _try_set_app_icon(self) -> None:
            try:
                ico = Path(__file__).parent.parent / "assets" / "app_icon.ico"
                if ico.exists():
                    self.iconbitmap(str(ico))
            except Exception:
                pass

        # ── Aufbau ─────────────────────────────────────────────────────────────

        def _build_ui(self) -> None:
            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=0)  # Toolbar
            self.rowconfigure(1, weight=0)  # Lizenz-Banner (versteckt wenn kein Ablauf)
            self.rowconfigure(2, weight=1)  # Hauptbereich
            self.rowconfigure(3, weight=0)  # Fußzeile
            if LICENSING_ENABLED:
                self._build_menu()
            self._build_toolbar()
            if LICENSING_ENABLED:
                self._build_expired_banner()
            self._build_main_area()
            self._build_footer()

        def _build_toolbar(self) -> None:
            p = self._p
            toolbar = ctk.CTkFrame(self, height=76, corner_radius=0,
                                   fg_color=("gray88", "gray14"))
            toolbar.grid(row=0, column=0, sticky="ew")
            toolbar.grid_propagate(False)
            toolbar.columnconfigure(2, weight=1)

            # Toolbar-Logo: transparentes PNG-Icon (64x64), Fallback auf Canvas
            _icon_png = Path(__file__).parent.parent / "assets" / "app_icon_toolbar.png"
            self._logo_canvas = None
            try:
                from PIL import Image as _PILImage
                _pil = _PILImage.open(_icon_png).resize((64, 64), _PILImage.LANCZOS)
                self._logo_image = ctk.CTkImage(
                    light_image=_pil, dark_image=_pil, size=(64, 64))
                ctk.CTkLabel(toolbar, image=self._logo_image, text="", width=66).grid(
                    row=0, column=0, padx=(12, 6), pady=6, sticky="w")
            except Exception:
                logo = tk.Canvas(toolbar, width=64, height=64,
                                 highlightthickness=0, bd=0, bg=p["toolbar_bg"])
                logo.grid(row=0, column=0, padx=(12, 6), pady=6, sticky="w")
                logo.create_line(4, 5, 4, 21, fill=ACCENT, width=2)
                for y in (7, 13, 19):
                    logo.create_rectangle(4, y - 2, 9, y + 2, fill=ACCENT, outline=ACCENT)
                    logo.create_line(9, y, 17, y, fill=ACCENT, width=2)
                    for x in (19, 23):
                        logo.create_rectangle(x, y - 2, x + 3, y + 2, fill=ACCENT, outline=ACCENT)
                self._logo_canvas = logo

            ctk.CTkLabel(toolbar, text="ETS GPA GA-Sync",
                         font=self._fonts["large"]).grid(
                row=0, column=1, padx=(0, 4), sticky="w")

            # Lizenz-Status-Indikator (klickbar, öffnet Lizenz-Dialog)
            # Nur sichtbar wenn LICENSING_ENABLED == True (config.py)
            if LICENSING_ENABLED:
                self._license_btn = ctk.CTkButton(
                    toolbar, text="…", width=130, height=30, corner_radius=6,
                    fg_color="transparent", border_width=1,
                    border_color=("gray60", "gray45"),
                    text_color=("gray15", "gray85"),
                    hover_color=("gray85", "gray25"),
                    font=self._fonts["body"],
                    command=self._open_license_dialog,
                )
                self._license_btn.grid(row=0, column=3, padx=(0, 12), sticky="e")

            # Theme-Toggle: ☀ = Light, ☾ = Dark
            ctk.CTkLabel(toolbar, text="☾",
                         font=self._fonts["normal"],
                         text_color="gray55").grid(row=0, column=4, padx=(0, 2), sticky="e")
            self._theme_switch = ctk.CTkSwitch(
                toolbar, text="", width=46,
                command=self._toggle_theme,
                onvalue="light", offvalue="dark",
                progress_color=ACCENT,
            )
            if self._theme_mode == "light":
                self._theme_switch.select()
            self._theme_switch.grid(row=0, column=5, padx=(0, 2), sticky="e")
            ctk.CTkLabel(toolbar, text="☀",
                         font=self._fonts["normal"],
                         text_color="gray55").grid(row=0, column=6, padx=(0, 10), sticky="e")

            ctk.CTkButton(toolbar, text="?", width=28, height=28, corner_radius=14,
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=self.show_help).grid(
                row=0, column=7, padx=(0, 12), sticky="e")

        # ── Lizenz-System ──────────────────────────────────────────────────────

        def _init_licensing(self) -> LicenseManager:
            """Erstellt und initialisiert den LicenseManager beim App-Start."""
            machine_id = get_machine_id()
            storage = LicenseStorage(machine_id=machine_id)
            trial = TrialManager()
            provider = NullProvider()  # Phase LIZENZ-3: Online-Provider eintragen
            mgr = LicenseManager(provider, storage, trial)
            mgr.ensure_trial_started()
            return mgr

        def _build_menu(self) -> None:
            """Erstellt die Menüleiste. Lizenz-Eintrag nur wenn LICENSING_ENABLED."""
            menubar = tk.Menu(self, tearoff=0)
            help_menu = tk.Menu(menubar, tearoff=0)
            if LICENSING_ENABLED:
                help_menu.add_command(label="Lizenz verwalten …", command=self._open_license_dialog)
                help_menu.add_separator()
            help_menu.add_command(label="Hilfe / Über …", command=self.show_help)
            menubar.add_cascade(label="Hilfe", menu=help_menu)
            self.configure(menu=menubar)

        def _build_expired_banner(self) -> None:
            """Baut das rote Ablauf-Banner (Row 1, initial unsichtbar)."""
            self._banner_frame = ctk.CTkFrame(
                self, corner_radius=0, fg_color=("#fff3cd", "#3d2800"),
                border_width=1, border_color=("#e6a817", "#7a5200"),
            )
            self._banner_frame.grid(row=1, column=0, sticky="ew")
            self._banner_frame.grid_remove()
            self._banner_frame.columnconfigure(0, weight=1)

            self._banner_label = ctk.CTkLabel(
                self._banner_frame,
                text="",
                font=self._fonts["body_bold"],
                text_color=("#7a4000", "#ffb84d"),
            )
            self._banner_label.grid(row=0, column=0, padx=16, pady=7, sticky="w")

            ctk.CTkButton(
                self._banner_frame,
                text="Lizenz aktivieren",
                width=150, height=28, corner_radius=5,
                fg_color=ACCENT, hover_color=ACCENT_DARK, text_color="white",
                font=self._fonts["body_bold"],
                command=self._open_license_dialog,
            ).grid(row=0, column=1, padx=(0, 12), pady=6, sticky="e")

        def _update_license_ui(self) -> None:
            """Aktualisiert Toolbar-Indikator und Banner anhand des Lizenzstatus."""
            if not hasattr(self, "_license_btn"):
                return
            info = self._license_manager.get_status()
            s = info.status

            if s == LicenseStatus.LICENSED:
                self._license_btn.configure(
                    text="✓  Pro",
                    fg_color=(ACCENT, "#1e6b12"),
                    text_color="white",
                    border_color=(ACCENT, "#1e6b12"),
                )
                if hasattr(self, "_banner_frame"):
                    self._banner_frame.grid_remove()

            elif s == LicenseStatus.TRIAL:
                days = info.days_remaining
                color = "#e6a817" if days <= 3 else ("gray60", "gray45")
                tc = "#7a4000" if days <= 3 else ("gray15", "gray85")
                self._license_btn.configure(
                    text=f"Trial: {days} Tage übrig",
                    fg_color="transparent",
                    text_color=tc,
                    border_color=color,
                )
                if hasattr(self, "_banner_frame"):
                    self._banner_frame.grid_remove()

            elif s == LicenseStatus.TRIAL_EXPIRED:
                self._license_btn.configure(
                    text="Trial abgelaufen",
                    fg_color=("#dc2626", "#7f1d1d"),
                    text_color="white",
                    border_color=("#dc2626", "#7f1d1d"),
                )
                if hasattr(self, "_banner_frame") and hasattr(self, "_banner_label"):
                    self._banner_label.configure(
                        text=f"⚠  Trial abgelaufen – bitte Lizenz erwerben unter {_LICENSE_URL}"
                    )
                    self._banner_frame.grid()

            elif s == LicenseStatus.LICENSE_INVALID:
                self._license_btn.configure(
                    text="Lizenz ungültig",
                    fg_color=("#dc2626", "#7f1d1d"),
                    text_color="white",
                    border_color=("#dc2626", "#7f1d1d"),
                )
                if hasattr(self, "_banner_frame"):
                    self._banner_frame.grid_remove()

            else:  # UNLICENSED / OFFLINE
                self._license_btn.configure(
                    text="Nicht lizenziert",
                    fg_color="transparent",
                    text_color=("gray15", "gray85"),
                    border_color=("gray60", "gray45"),
                )
                if hasattr(self, "_banner_frame"):
                    self._banner_frame.grid_remove()

        def _open_license_dialog(self) -> None:
            """Öffnet den modalen Lizenz-Verwaltungs-Dialog."""
            dialog = ctk.CTkToplevel(self)
            dialog.title("Lizenz verwalten")
            dialog.geometry("520x400")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grab_set()
            dialog.columnconfigure(0, weight=1)

            info = self._license_manager.get_status()
            s = info.status

            # Status-Anzeige
            if s == LicenseStatus.LICENSED:
                status_text, status_color = "✓  Lizenz aktiv (Pro)", ACCENT
            elif s == LicenseStatus.TRIAL:
                status_text = f"⏱  Trial aktiv – {info.days_remaining} Tage verbleibend"
                status_color = "#e6a817"
            elif s == LicenseStatus.TRIAL_EXPIRED:
                status_text, status_color = "✕  Trial abgelaufen", "#dc2626"
            elif s == LicenseStatus.LICENSE_INVALID:
                status_text, status_color = "✕  Lizenz ungültig", "#dc2626"
            else:
                status_text, status_color = "–  Kein Lizenzstatus", "gray"

            ctk.CTkLabel(dialog, text="Lizenzstatus",
                         font=self._fonts["normal"]).grid(
                row=0, column=0, padx=24, pady=(20, 4), sticky="w")

            ctk.CTkLabel(dialog, text=status_text,
                         font=self._fonts["body"],
                         text_color=status_color).grid(
                row=1, column=0, padx=24, pady=(0, 16), sticky="w")

            # Trennlinie
            tk.Frame(dialog, height=1, bg=self._p["border"]).grid(
                row=2, column=0, sticky="ew", padx=24, pady=(0, 16))

            # Lizenz-Blob-Eingabe
            ctk.CTkLabel(dialog, text="Lizenzschlüssel / Lizenz-Blob einfügen:",
                         font=self._fonts["body"]).grid(
                row=3, column=0, padx=24, pady=(0, 6), sticky="w")

            key_text = tk.Text(dialog, height=6, font=TTK_BODY,
                               relief="solid", bd=1, wrap="word")
            key_text.grid(row=4, column=0, padx=24, pady=(0, 10), sticky="ew")

            msg_var = tk.StringVar()
            msg_label = ctk.CTkLabel(dialog, textvariable=msg_var,
                                     font=self._fonts["body"],
                                     text_color=("gray30", "gray70"))
            msg_label.grid(row=5, column=0, padx=24, pady=(0, 4), sticky="w")

            def do_activate():
                blob = key_text.get("1.0", "end").strip()
                if not blob:
                    msg_var.set("Bitte Lizenz-Blob eingeben.")
                    return
                result = self._license_manager.activate(blob)
                if result.success:
                    msg_var.set("✓  Lizenz erfolgreich aktiviert.")
                    self._update_license_ui()
                    self.after(1200, dialog.destroy)
                else:
                    msg_var.set(f"✕  {result.message}")

            def do_deactivate():
                ok = self._license_manager.deactivate()
                if ok:
                    msg_var.set("Lizenz deaktiviert.")
                    self._update_license_ui()
                else:
                    msg_var.set("Deaktivierung fehlgeschlagen.")

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.grid(row=6, column=0, padx=24, pady=(4, 20), sticky="ew")
            btn_frame.columnconfigure(0, weight=1)

            ctk.CTkButton(btn_frame, text="Aktivieren", fg_color=ACCENT,
                          hover_color=ACCENT_DARK, text_color="white",
                          command=do_activate).grid(row=0, column=0, sticky="w")
            ctk.CTkButton(btn_frame, text="Deaktivieren",
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=do_deactivate).grid(row=0, column=1, padx=(8, 0), sticky="w")
            ctk.CTkButton(btn_frame, text="Schließen",
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=dialog.destroy).grid(row=0, column=2, padx=(8, 0), sticky="w")

        def _build_main_area(self) -> None:
            main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
            main.grid(row=2, column=0, sticky="nsew", padx=18, pady=(8, 14))
            main.columnconfigure(0, weight=1, minsize=600)
            main.columnconfigure(1, weight=0, minsize=300)
            main.rowconfigure(0, weight=1)

            workspace = ctk.CTkFrame(main, corner_radius=0, fg_color="transparent")
            workspace.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
            workspace.columnconfigure(0, weight=1)
            workspace.rowconfigure(0, weight=0)
            workspace.rowconfigure(1, weight=0)
            workspace.rowconfigure(2, weight=1)

            self._build_import_top(workspace)
            self._build_kpi_row(workspace)
            self._build_center_panel(workspace)
            self._build_right_panel(main)

        def _card(self, parent, row: int, column: int = 0, columnspan: int = 1,
                  sticky: str = "nsew", padx=(0, 0), pady=(0, 0)) -> ctk.CTkFrame:
            frame = ctk.CTkFrame(parent, corner_radius=8, border_width=1,
                                 border_color=("gray78", "gray28"))
            frame.grid(row=row, column=column, columnspan=columnspan,
                       sticky=sticky, padx=padx, pady=pady)
            return frame

        def _build_upload_box(self, parent, title: str, drop_text: str,
                               var: tk.StringVar, button_text: str,
                               command) -> ctk.CTkFrame:
            card = self._card(parent, 0, 0)
            card.columnconfigure(0, weight=1)

            ctk.CTkLabel(card, text=title,
                         font=self._fonts["normal"],
                         anchor="w").grid(row=0, column=0, sticky="w", padx=12, pady=(8, 4))

            # Keine feste height= und kein grid_propagate(False) → Container wächst bei
            # hoher DPI-Skalierung mit dem Text mit (verhindert abgeschnittene Texte).
            drop_zone = ctk.CTkFrame(card, corner_radius=6, border_width=1,
                                     border_color=(ACCENT_DARK, ACCENT),
                                     fg_color=("gray96", "gray18"))
            drop_zone.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
            drop_zone.columnconfigure(0, weight=1)
            ctk.CTkLabel(drop_zone, text=drop_text,
                         text_color=("gray45", "gray60"),
                         font=self._fonts["body"],
                         anchor="center",
                         wraplength=200).grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

            ctk.CTkLabel(card, textvariable=var,
                         text_color=("gray35", "gray65"),
                         font=self._fonts["body"],
                         wraplength=200, anchor="w").grid(
                row=2, column=0, sticky="ew", padx=12, pady=(0, 4))

            ctk.CTkButton(card, text=button_text,
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray88", "gray25"),
                          font=self._fonts["body_bold"],
                          command=command).grid(
                row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

            return drop_zone

        def _build_import_top(self, parent) -> None:
            box = self._card(parent, 0, pady=(0, 8))
            box.columnconfigure(0, weight=1)
            box.columnconfigure(1, weight=1)
            box.columnconfigure(2, weight=0, minsize=160)

            ctk.CTkLabel(box, text="Datenquellen importieren",
                         font=self._fonts["normal"],
                         anchor="w").grid(row=0, column=0, columnspan=3,
                                          sticky="w", padx=14, pady=(10, 4))

            gpa_holder = ctk.CTkFrame(box, corner_radius=0, fg_color="transparent")
            gpa_holder.grid(row=1, column=0, sticky="nsew", padx=(14, 8), pady=(0, 10))
            gpa_holder.columnconfigure(0, weight=1)
            self.gpa_drop = self._build_upload_box(
                gpa_holder, "GPA-Projekt",
                "☁  .gpa hier ablegen",
                self.gpa_var, ".gpa auswählen…", self.pick_gpa)

            ets_holder = ctk.CTkFrame(box, corner_radius=0, fg_color="transparent")
            ets_holder.grid(row=1, column=1, sticky="nsew", padx=(0, 8), pady=(0, 10))
            ets_holder.columnconfigure(0, weight=1)
            self.ets_drop = self._build_upload_box(
                ets_holder, "ETS-Gruppenadressen",
                "☁  .xml/.knxproj hier ablegen",
                self.ets_var, ".xml/.knxproj wählen…", self.pick_ets)

            action = ctk.CTkFrame(box, corner_radius=0, fg_color="transparent")
            action.grid(row=1, column=2, sticky="sew", padx=(0, 14), pady=(0, 10))
            action.columnconfigure(0, weight=1)
            self.analyze_button = ctk.CTkButton(
                action, text="Analysieren",
                fg_color=ACCENT, hover_color=ACCENT_DARK,
                text_color="white",
                font=self._fonts["body_bold"],
                width=140, height=30, command=self.analyze)
            self.analyze_button.grid(row=0, column=0, sticky="ew")

        def _build_kpi_row(self, parent) -> None:
            row = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
            row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
            for i in range(4):
                row.columnconfigure(i, weight=1, uniform="kpi")

            kpi_defs = [
                ("gpa", "GPA-Datenpunkte", self.kpi_vars["gpa"],      "#009b68"),
                ("ets", "ETS-Adressen",    self.kpi_vars["ets"],      "#009b68"),
                ("⚠",  "Unterschiede",     self.kpi_vars["diff"],     "#f59e0b"),
                ("✓",  "Ausgewählt",        self.kpi_vars["selected"], "#16a34a"),
            ]
            self._kpi_canvases: List[tk.Canvas] = []
            for col, (icon, title, var, color) in enumerate(kpi_defs):
                card = self._card(row, 0, col, padx=(0, 10) if col < 3 else (0, 0))
                card.columnconfigure(1, weight=1)
                if icon == "gpa":
                    icon_widget = self._make_gpa_kpi_icon(card)
                    self._gpa_kpi_canvas = icon_widget
                    self._kpi_canvases.append(icon_widget)
                elif icon == "ets":
                    icon_widget = self._make_ets_kpi_icon(card)
                    self._kpi_canvases.append(icon_widget)
                else:
                    icon_widget = ctk.CTkLabel(card, text=icon,
                                               font=self._fonts["large"],
                                               text_color=color, width=44)
                icon_widget.grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="w")
                ctk.CTkLabel(card, text=title,
                             font=self._fonts["body"],
                             anchor="w").grid(
                    row=0, column=1, sticky="w", padx=(0, 10), pady=(8, 0))
                ctk.CTkLabel(card, textvariable=var,
                             font=self._fonts["kpi"],
                             anchor="w").grid(
                    row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 8))

        def _build_center_panel(self, parent) -> None:
            center = self._card(parent, 2)
            center.columnconfigure(0, weight=1)
            center.rowconfigure(2, weight=1)

            ctk.CTkLabel(center, text="Datenpunkte – Änderungen",
                         font=self._fonts["normal"],
                         anchor="w").grid(row=0, column=0, sticky="w",
                                          padx=16, pady=(12, 6))

            # Toolbar
            tbar = ctk.CTkFrame(center, corner_radius=0, fg_color="transparent")
            tbar.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
            # Spalte 3 = Suchfeld (stretcht/schrumpft); 4 = Sync (feste Breite)
            tbar.columnconfigure(3, weight=1, minsize=80)

            _btn = dict(fg_color="transparent", border_width=1,
                        border_color=("gray70", "gray40"),
                        text_color=("gray15", "gray85"),
                        font=self._fonts["body"], height=30)

            self.select_all_button = ctk.CTkButton(
                tbar, text="✓  Alle auswählen",
                command=self.select_all, **_btn)
            self.select_all_button.grid(row=0, column=0, sticky="w", padx=(0, 8))

            self.deselect_all_button = ctk.CTkButton(
                tbar, text="✕  Alle abwählen",
                command=self.deselect_all, **_btn)
            self.deselect_all_button.grid(row=0, column=1, sticky="w", padx=(0, 8))

            self.csv_button = ctk.CTkButton(
                tbar, text="CSV-Export",
                command=self.save_csv, **_btn)
            self.csv_button.grid(row=0, column=2, sticky="w", padx=(0, 8))

            # Suchfeld: Rahmen-Frame + Lupe/Clear-Toggle + borderless Entry
            self._search_frame = ctk.CTkFrame(
                tbar, corner_radius=6, border_width=1,
                border_color=("gray60", "gray45"),
                fg_color=("white", "#363636"), height=34)
            self._search_frame.grid(row=0, column=3, sticky="ew", padx=(0, 8))
            self._search_frame.grid_propagate(False)
            self._search_frame.columnconfigure(1, weight=1)
            self._search_frame.rowconfigure(0, weight=1)

            # Lupe (sichtbar wenn Suchfeld leer)
            self._search_icon = ctk.CTkLabel(
                self._search_frame, text="🔍", width=28,
                font=self._fonts["large"])
            self._search_icon.grid(row=0, column=0, padx=(5, 0), sticky="w")

            # Clear-Button (sichtbar wenn Text vorhanden)
            self._search_clear = ctk.CTkLabel(
                self._search_frame, text="✕", width=28,
                font=self._fonts["normal"],
                text_color=("gray40", "gray65"), cursor="hand2")
            self._search_clear.bind("<Button-1>", lambda _: self.filter_var.set(""))
            self._search_clear.bind("<Enter>",
                lambda _: self._search_clear.configure(text_color=("gray15", "gray90")))
            self._search_clear.bind("<Leave>",
                lambda _: self._search_clear.configure(text_color=("gray40", "gray65")))

            self.search_entry = ctk.CTkEntry(
                self._search_frame, textvariable=self.filter_var,
                placeholder_text="Suchen…",
                font=self._fonts["body"],
                border_width=0, fg_color="transparent")
            self.search_entry.grid(row=0, column=1, sticky="ew", padx=(2, 4), pady=2)

            def _on_filter_change(*_) -> None:
                if self.filter_var.get():
                    self._search_icon.grid_remove()
                    self._search_clear.grid(row=0, column=0, padx=(5, 0), sticky="w")
                else:
                    self._search_clear.grid_remove()
                    self._search_icon.grid(row=0, column=0, padx=(5, 0), sticky="w")
                self.refresh_tree()

            self.filter_var.trace_add("write", _on_filter_change)
            self.search_entry.bind("<FocusIn>",
                lambda _: self._search_frame.configure(border_color=(ACCENT_DARK, ACCENT)))
            self.search_entry.bind("<FocusOut>",
                lambda _: self._search_frame.configure(border_color=("gray60", "gray45")))

            self.sync_button = ctk.CTkButton(
                tbar, text="Synchronisieren",
                fg_color=ACCENT, hover_color=ACCENT_DARK,
                text_color="white",
                font=self._fonts["body_bold"],
                width=150, height=30, state="disabled", command=self.sync)
            self.sync_button.grid(row=0, column=4, sticky="e")
            center.bind("<Configure>", self._on_center_resize)

            # Tabelle
            table_frame = ctk.CTkFrame(center, corner_radius=0, fg_color="transparent")
            table_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 10))
            table_frame.columnconfigure(0, weight=1)
            table_frame.rowconfigure(0, weight=1)

            cols = ("status", "ga", "old", "new")
            self.tree = ttk.Treeview(table_frame, columns=cols,
                                     show="tree headings", selectmode="extended")
            self._refresh_headings()
            self.tree.column("#0",     width=58,  minwidth=58,  anchor="center", stretch=False)
            self.tree.column("status", width=120, minwidth=100, anchor="w",      stretch=False)
            self.tree.column("ga",     width=100, minwidth=90,  anchor="w",      stretch=False)
            self.tree.column("old",    width=300, minwidth=180, anchor="w",      stretch=True)
            self.tree.column("new",    width=420, minwidth=240, anchor="w",      stretch=True)
            self.tree.grid(row=0, column=0, sticky="nsew")

            yscroll = ctk.CTkScrollbar(table_frame, command=self.tree.yview)
            self.tree.configure(yscrollcommand=yscroll.set)
            yscroll.grid(row=0, column=1, sticky="ns")

            self.table_count_var = tk.StringVar(value="")

            self.tree.bind("<Button-1>",       self.on_tree_click)
            self.tree.bind("<Double-1>",       self.on_tree_double_click)
            self.tree.bind("<F2>",             lambda _e: self.edit_focused_new_name())
            self.tree.bind("<space>",          lambda _e: self.toggle_selected_rows())
            self.tree.bind("<Control-c>",      self.copy_selected_rows)
            self.tree.bind("<Control-C>",      self.copy_selected_rows)
            self.tree.bind("<Button-3>",       self.show_tree_context_menu)
            self.tree.bind("<Button-2>",       self.show_tree_context_menu)
            self.tree.bind("<<TreeviewSelect>>", lambda _e: self.update_details())

            p = self._p
            self.tree_menu = tk.Menu(self, tearoff=0,
                                     bg=p["panel"], fg=p["text"],
                                     activebackground=p["soft_green"],
                                     activeforeground=p["text"])
            self.tree_menu.add_command(label="Auswahl für Excel kopieren",
                                       command=self.copy_selected_rows_excel)
            self.tree_menu.add_command(label="Auswahl als CSV kopieren",
                                       command=self.copy_selected_rows_csv)
            self.tree_menu.add_separator()
            self.tree_menu.add_command(label="Alle sichtbaren Zeilen für Excel kopieren",
                                       command=self.copy_visible_rows_excel)

        def _build_right_panel(self, parent) -> None:
            right = self._card(parent, 0, column=1, sticky="nsew")
            right.columnconfigure(0, weight=1)
            right.grid_propagate(False)
            right.configure(width=300)

            ctk.CTkLabel(right, text="Eigenschaften",
                         font=self._fonts["normal"],
                         anchor="w").grid(row=0, column=0, sticky="w",
                                          padx=16, pady=(14, 4))

            form = ctk.CTkFrame(right, corner_radius=0, fg_color="transparent")
            form.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
            form.columnconfigure(0, weight=1)

            ctk.CTkLabel(form, text="Ausgewählter Datenpunkt",
                         font=self._fonts["normal"],
                         anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 4))

            def add_field(label: str, var_name: str, readonly: bool = True,
                          row: int = 0) -> ctk.CTkEntry:
                ctk.CTkLabel(form, text=label, text_color=("gray30", "gray65"),
                             font=self._fonts["body"],
                             anchor="w").grid(row=row, column=0, sticky="w", pady=(6, 1))
                entry = ctk.CTkEntry(
                    form, textvariable=self.detail_vars[var_name],
                    state="readonly" if readonly else "normal",
                    font=self._fonts["body"],
                    text_color=("#1a1a1a", "#e8e8e8"))
                entry.grid(row=row + 1, column=0, sticky="ew")
                return entry

            add_field("Status",               "status", row=1)
            add_field("Gruppenadresse",        "ga",     row=3)
            add_field("Quelle",                "source", row=5)
            add_field("Aktueller Name (GPA)",  "old",    row=7)
            self.detail_new_entry = add_field("Neuer Name (GPA)", "new",
                                              readonly=False, row=9)
            self.detail_new_entry.bind("<KeyRelease>", self.on_detail_new_name_changed)
            self.detail_new_entry.bind("<Return>",     self.on_detail_new_name_changed)

            p = self._p
            self._info_frame = tk.Frame(form, bg=p["info_bg"],
                                        highlightbackground=p["info_border"],
                                        highlightthickness=1)
            self._info_frame.grid(row=11, column=0, sticky="ew", pady=(16, 10))
            self._info_label = tk.Label(
                self._info_frame,
                text='ⓘ  Der neue Name kann hier beliebig angepasst werden, bevor die Synchronisation durchgeführt wird.',
                bg=p["info_bg"], fg=p["info_fg"],
                font=TTK_BODY, anchor="w", justify="left", wraplength=260)
            self._info_label.pack(fill="x", padx=10, pady=10)

        def _build_footer(self) -> None:
            p = self._p
            # Keine feste height= und kein grid_propagate(False) → Fußzeile passt sich
            # der skalierten Schrift an (verhindert abgeschnittene Texte bei 150%/200%).
            footer = tk.Frame(self, bg=p["bg"])
            footer.grid(row=3, column=0, sticky="ew")
            footer.columnconfigure(0, weight=1)
            self._footer_frame = footer

            # TTK_BODY (12pt Segoe UI) – DPI-skaliert über native Tk-Punktgröße
            self._status_label = tk.Label(
                footer, textvariable=self.status_var,
                bg=p["bg"], fg=p["text"], anchor="w", font=TTK_SMALL)
            self._status_label.grid(row=0, column=0, sticky="nsew", padx=12, pady=5)

            self.progress_bar = ttk.Progressbar(
                footer, mode="indeterminate", length=140,
                style="Sync.Horizontal.TProgressbar")
            self.progress_bar.grid(row=0, column=1, padx=(0, 8), pady=5)
            self.progress_bar.grid_remove()

            self._hint_label = tk.Label(
                footer,
                text="Bearbeiten: Doppelklick/F2 | Kopieren: Rechtsklick / Strg+C",
                bg=p["bg"], fg=p["muted"], font=TTK_SMALL)
            self._hint_label.grid(row=0, column=2, sticky="e", padx=12, pady=5)

            self._version_label = tk.Label(
                footer, text=f"v{__version__}",
                bg=p["bg"], fg=p["muted"], font=TTK_SMALL)
            self._version_label.grid(row=0, column=3, sticky="e", padx=(0, 12), pady=5)

        # ── Drag & Drop ────────────────────────────────────────────────────────

        def _register_tooltips(self) -> None:
            T = _Tooltip
            T(self.gpa_drop,
              "GPA-Projektdatei (.gpa) per Drag & Drop ablegen\noder über den Button auswählen.")
            T(self.ets_drop,
              "ETS-Gruppenadressen-Export (.xml) oder ETS-Projekt (.knxproj)\nper Drag & Drop ablegen oder über den Button auswählen.")
            T(self.analyze_button,
              "Vergleicht GPA-Datenpunkte mit ETS-Gruppenadressen\nund listet alle Unterschiede in der Tabelle auf.")
            T(self.select_all_button,
              "Markiert alle aktuell sichtbaren Zeilen\nfür die Synchronisation.")
            T(self.deselect_all_button,
              "Entfernt die Markierung aller aktuell sichtbaren Zeilen.")
            T(self.csv_button,
              "Exportiert die angezeigte Tabelle als CSV-Datei.")
            T(self._search_frame,
              "Filtert die Tabelle in Echtzeit.\nDurchsucht Adresse, GA, Namen und Status.")
            T(self.sync_button,
              "Erstellt eine neue GPA-Datei mit den ausgewählten\nNamens-Änderungen. Die Originaldatei bleibt unverändert.")
            T(self._theme_switch,
              "Design zwischen Hell und Dunkel wechseln.")

        def _setup_drop_targets(self) -> None:
            if not DND_AVAILABLE:
                return
            for widget in [self, self.gpa_drop, self.ets_drop, self.tree]:
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self.handle_drop)
                except Exception:
                    pass

        def _first_dropped_file(self, raw: str) -> Optional[str]:
            try:
                parts = self.tk.splitlist(raw)
            except Exception:
                parts = [raw]
            if not parts:
                return None
            return str(parts[0]).strip().strip("{}")

        def handle_drop(self, event) -> None:
            path = self._first_dropped_file(event.data)
            if not path:
                return
            lower = path.lower()
            if lower.endswith((".gpa", ".zip")):
                self.gpa_var.set(path)
                self.status_var.set(f"GPA-Projekt übernommen: {_shorten_path(path)}")
            elif lower.endswith((".xml", ".knxproj")):
                self.ets_var.set(path)
                self.status_var.set(f"ETS-Datei übernommen: {_shorten_path(path)}")
            else:
                messagebox.showinfo("Nicht erkannt",
                                    "Bitte eine .gpa/.zip-, .xml- oder .knxproj-Datei ablegen.")

        # ── Datei-Auswahl ──────────────────────────────────────────────────────

        def pick_gpa(self) -> None:
            path = filedialog.askopenfilename(
                filetypes=[("GPA-Projekt", "*.gpa"), ("ZIP-Archiv", "*.zip"),
                           ("Alle Dateien", "*.*")])
            if path:
                self.gpa_var.set(path)
                self.status_var.set(f"GPA-Projekt ausgewählt: {_shorten_path(path)}")

        def pick_ets(self) -> None:
            path = filedialog.askopenfilename(
                filetypes=[("ETS-Gruppenadressen", "*.xml *.knxproj"), ("ETS-XML", "*.xml"),
                           ("ETS-Projekt", "*.knxproj"), ("Alle Dateien", "*.*")])
            if path:
                self.ets_var.set(path)
                self.status_var.set(f"ETS-Datei ausgewählt: {_shorten_path(path)}")

        def _pwd(self) -> Optional[str]:
            pwd = self.pwd_var.get()
            return pwd if pwd else None

        def _gpa_archive_is_encrypted(self, gpa_path: Path) -> bool:
            try:
                with zipfile.ZipFile(gpa_path, "r") as zf:
                    return any(info.flag_bits & 0x1 for info in zf.infolist())
            except Exception:
                return False

        def _ensure_password_if_needed(self, gpa_path: Path) -> bool:
            if not self._gpa_archive_is_encrypted(gpa_path):
                return True
            if self.pwd_var.get():
                return True
            pwd = simpledialog.askstring(
                "GPA-ZIP-Passwort erforderlich",
                "Das GPA-Archiv ist ZIP-verschlüsselt. Bitte Passwort eingeben:",
                show="*", parent=self)
            if pwd is None:
                return False
            self.pwd_var.set(pwd)
            return True

        # ── Resize-Handler ─────────────────────────────────────────────────────

        def _on_center_resize(self, event) -> None:
            if not hasattr(self, "sync_button"):
                return
            width = getattr(event, "width", 0) or 0
            if width < 500:
                # Sehr schmales Layout (z.B. 175-200% DPI auf kleinem Monitor)
                self.sync_button.configure(text="Sync")
                if hasattr(self, "select_all_button"):
                    self.select_all_button.configure(text="Wählen")
                    self.deselect_all_button.configure(text="Abwählen")
                    self.csv_button.configure(text="CSV")
            else:
                # Normales Layout
                self.sync_button.configure(text="Synchronisieren")
                if hasattr(self, "select_all_button"):
                    self.select_all_button.configure(text="✓  Alle auswählen")
                    self.deselect_all_button.configure(text="✕  Alle abwählen")
                    self.csv_button.configure(text="CSV-Export")

        # ── Tabellen-Spalten ───────────────────────────────────────────────────

        def _heading_text(self, column: str) -> str:
            base = self.heading_titles.get(column, column)
            if self.sort_column != column:
                return base
            return base + ("  ▼" if self.sort_reverse else "  ▲")

        def _refresh_headings(self) -> None:
            if not hasattr(self, "tree"):
                return
            for col in ("#0", "status", "ga", "old", "new"):
                try:
                    self.tree.heading(col, text=self._heading_text(col), anchor="w",
                                      command=lambda c=col: self.sort_by_column(c))
                except Exception:
                    pass

        def sort_by_column(self, column: str) -> None:
            self._destroy_edit_entry()
            if self.sort_column == column:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_column = column
                self.sort_reverse = False

            def key(c: SyncCandidate):
                if column == "#0":
                    return (0 if c.selected else 1, c.status.lower(), c.group_address_value, c.current_name.lower())
                if column == "status":
                    return (c.status.lower(), c.group_address_value, c.current_name.lower())
                if column == "ga":
                    return (c.group_address_value, c.group_address)
                if column == "old":
                    return (c.current_name.lower(), c.group_address_value)
                if column == "new":
                    return (c.new_name.lower(), c.group_address_value)
                return (c.group_address_value, c.current_name.lower())

            self.candidates.sort(key=key, reverse=self.sort_reverse)
            self.refresh_tree()
            self._refresh_headings()

        # ── Hilfe ──────────────────────────────────────────────────────────────

        def show_help(self) -> None:
            messagebox.showinfo("Hilfe – ETS GPA GA-Sync",
                'Zweck:\n'
                'Dieses Tool übernimmt Gruppenadressnamen aus einem ETS-Export in ein GPA-Projekt. '
                'Synchronisiert wird nur in Richtung ETS → GPA.\n\n'
                'Ablauf:\n'
                '1. GPA-Projekt (.gpa) ablegen oder auswählen.\n'
                '2. ETS-Gruppenadressen-Export (.xml) oder ETS-Projekt (.knxproj) ablegen oder auswählen.\n'
                '3. Auf „Analysieren“ klicken.\n'
                '4. Änderungen prüfen und bei Bedarf einzelne Zeilen abwählen.\n'
                '5. Mit „Synchronisieren + speichern“ eine neue GPA-Datei erzeugen.\n\n'
                'Wichtig:\n'
                'Das Originalprojekt wird nicht verändert. Im GPA-Projekt wird nur der sichtbare '
                'Datenpunktname geändert. LogicalName und Gruppenadressen bleiben unverändert.\n\n'
                'Hinweise:\n'
                '• Mit Doppelklick oder F2 kann der neue GPA-Name direkt in der Liste bearbeitet werden.\n'
                '• Mit Rechtsklick oder Strg+C können markierte Zeilen nach Excel kopiert werden.\n'
                '• Wenn nur eine Datei geladen ist, wird trotzdem eine reine Kontrollliste angezeigt.\n'
                '• .knxproj-Dateien können ein ETS-Projektpasswort benötigen.\n'
                '• Reine Leerzeichen-Unterschiede werden als „Leerzeichen“ markiert.\n'
                '• GPA-Adressen ohne Treffer im ETS-Export werden als „Nicht in ETS“ angezeigt.')

        # ── Status / KPIs ──────────────────────────────────────────────────────

        def _update_summary(self, datapoints_count: Optional[int] = None,
                            ets_count: Optional[int] = None) -> None:
            total = len(self.candidates)
            selected = sum(1 for c in self.candidates
                           if c.selected and c.status in (SyncStatus.AENDERUNG, SyncStatus.LEERZEICHEN))
            visible = len(self.visible_iids)
            if datapoints_count is not None and ets_count is not None:
                self.kpi_vars["gpa"].set(f"{datapoints_count:,}".replace(",", "."))
                self.kpi_vars["ets"].set(f"{ets_count:,}".replace(",", "."))
            self.kpi_vars["diff"].set(str(total))
            self.kpi_vars["selected"].set(str(selected))
            if hasattr(self, "table_count_var"):
                self.table_count_var.set(f"Zeilen: {visible} von {total}")

        def _set_busy(self, busy: bool) -> None:
            state = "disabled" if busy else "normal"
            for attr in ("analyze_button", "select_all_button", "deselect_all_button", "csv_button"):
                widget = getattr(self, attr, None)
                if widget is not None:
                    try:
                        widget.configure(state=state)
                    except Exception:
                        pass
            if hasattr(self, "sync_button"):
                if busy:
                    self.sync_button.configure(state="disabled")
                else:
                    can_sync = any(c.selected and c.status == SyncStatus.AENDERUNG
                                   for c in self.candidates)
                    self.sync_button.configure(state="normal" if can_sync else "disabled")
            if busy:
                self.progress_bar.grid()
                self.progress_bar.start(12)
            else:
                self.progress_bar.stop()
                self.progress_bar.grid_remove()

        # ── Analyse ────────────────────────────────────────────────────────────

        def analyze(self) -> None:
            self._destroy_edit_entry()
            gpa_text = self.gpa_var.get().strip()
            ets_text = self.ets_var.get().strip()
            gpa = Path(gpa_text) if gpa_text else None
            ets = Path(ets_text) if ets_text else None

            if gpa is None and ets is None:
                messagebox.showwarning("Hinweis",
                    "Bitte mindestens ein GPA-Projekt oder eine ETS-XML auswählen.")
                return
            if gpa is not None and not gpa.exists():
                messagebox.showerror("Fehler", "GPA-Datei nicht gefunden.")
                return
            if ets is not None and not ets.exists():
                messagebox.showerror("Fehler", "ETS-XML nicht gefunden.")
                return
            if gpa is not None and not self._ensure_password_if_needed(gpa):
                self.status_var.set("Analyse abgebrochen: GPA-ZIP-Passwort nicht eingegeben.")
                return

            gpa_pwd = self._pwd()
            self._set_busy(True)
            self.status_var.set("Analyse läuft …")

            def worker() -> None:
                try:
                    datapoints: List[GpaDatapoint] = (
                        parse_gpa_datapoints(gpa, gpa_pwd) if gpa is not None else []
                    )
                    ets_map: Dict[int, EtsGroupAddress] = {}
                    if ets is not None:
                        try:
                            ets_map = parse_ets_ga_export(ets)
                        except EtsProjectPasswordRequired:
                            result_q: queue.Queue[Optional[str]] = queue.Queue()

                            def ask_ets_pwd() -> None:
                                pwd = simpledialog.askstring(
                                    "ETS-Projektpasswort erforderlich",
                                    "Die .knxproj-Datei enthält verschlüsselte Projektbestandteile.\n"
                                    "Bitte das ETS-Projektpasswort eingeben:",
                                    show="*", parent=self)
                                result_q.put(pwd)

                            self.after(0, ask_ets_pwd)
                            ets_pwd = result_q.get()
                            if ets_pwd is None:
                                self.after(0, lambda: self._analyze_cancelled(
                                    "Analyse abgebrochen: ETS-Projektpasswort nicht eingegeben."))
                                return
                            ets_map = parse_ets_ga_export(ets, project_password=ets_pwd)

                    candidates = (
                        build_sync_candidates(datapoints, ets_map)
                        if datapoints and ets_map
                        else build_partial_candidates(datapoints, ets_map)
                    )
                    candidates.sort(key=lambda c: (
                        c.group_address_value, c.group_address, c.current_name.lower()))
                    self.after(0, lambda: self._analyze_done(datapoints, ets_map, candidates))
                except Exception as exc:
                    self.after(0, lambda e=exc: self._analyze_error(e))

            threading.Thread(target=worker, daemon=True).start()

        def _analyze_cancelled(self, message: str) -> None:
            self._set_busy(False)
            self.status_var.set(message)

        def _analyze_done(self, datapoints: List[GpaDatapoint],
                          ets_map: Dict[int, EtsGroupAddress],
                          candidates: List[SyncCandidate]) -> None:
            _log.info("Analyse abgeschlossen: %d Datenpunkte, %d ETS-GAs, %d Kandidaten",
                      len(datapoints), len(ets_map), len(candidates))
            self.candidates = candidates
            self.datapoint_name_by_path = {dp.zip_path: dp.entity_name for dp in datapoints}
            self.sort_column = "ga"
            self.sort_reverse = False
            self._set_busy(False)
            self.refresh_tree()
            self._update_summary(len(datapoints), len(ets_map))
            if datapoints and ets_map:
                self.status_var.set(
                    f"Analyse fertig: {len(datapoints)} GPA-Datenpunkte, "
                    f"{len(ets_map)} ETS-Gruppenadressen, {len(candidates)} Unterschiede gefunden.")
            elif datapoints:
                self.status_var.set(
                    f"GPA analysiert: {len(datapoints)} GPA-Datenpunkte gefunden und in der Liste angezeigt. "
                    "Für Unterschiede zusätzlich eine ETS-XML auswählen.")
            else:
                self.status_var.set(
                    f"ETS-XML analysiert: {len(ets_map)} ETS-Gruppenadressen gefunden und in der Liste angezeigt. "
                    "Für Unterschiede zusätzlich ein GPA-Projekt auswählen.")

        def _analyze_error(self, error: Exception) -> None:
            _log.error("Analysefehler: %s", error, exc_info=True)
            self._set_busy(False)
            self.status_var.set("Analyse fehlgeschlagen.")
            messagebox.showerror("Fehler bei Analyse", str(error))

        # ── Filter ─────────────────────────────────────────────────────────────

        def clear_filter(self) -> None:
            self.filter_var.set("")

        def _row_matches_filter(self, c: SyncCandidate, needle: str) -> bool:
            if not needle:
                return True
            haystack = " | ".join([c.status, c.group_address, c.source_field,
                                    c.current_name, c.new_name, c.zip_path]).lower()
            return needle in haystack

        # ── Tabelle ────────────────────────────────────────────────────────────

        def refresh_tree(self) -> None:
            self._destroy_edit_entry()
            current_selection = set(self.tree.selection()) if hasattr(self, "tree") else set()
            self.tree.delete(*self.tree.get_children())
            needle = self.filter_var.get().strip().lower()
            self.visible_iids = []
            visible_counter = 0
            for idx, c in enumerate(self.candidates):
                if not self._row_matches_filter(c, needle):
                    continue
                mark = "✓" if c.selected else ""
                iid = str(idx)
                tags = ["even" if visible_counter % 2 == 0 else "odd"]
                if c.status == SyncStatus.AENDERUNG and c.selected:
                    tags.append("selected_sync")
                elif c.status == SyncStatus.AENDERUNG:
                    tags.append("unselected_sync")
                if c.status == SyncStatus.MEHRDEUTIG:
                    mark = "!"
                    tags.append("ambiguous")
                self.tree.insert("", "end", iid=iid, text=mark,
                                 values=(c.status, c.group_address, c.current_name, c.new_name),
                                 tags=tuple(tags))
                self.visible_iids.append(iid)
                visible_counter += 1
            for iid in current_selection:
                if self.tree.exists(iid):
                    self.tree.selection_add(iid)
            self._update_summary()
            self.update_details()
            self._refresh_headings()
            if hasattr(self, "sync_button"):
                can_sync = any(c.selected and c.status == SyncStatus.AENDERUNG
                               for c in self.candidates)
                self.sync_button.configure(state="normal" if can_sync else "disabled")

        def select_all(self) -> None:
            visible = set(self.visible_iids)
            for idx, c in enumerate(self.candidates):
                if c.status == SyncStatus.AENDERUNG and str(idx) in visible:
                    c.selected = True
            self.refresh_tree()

        def deselect_all(self) -> None:
            visible = set(self.visible_iids)
            for idx, c in enumerate(self.candidates):
                if str(idx) in visible:
                    c.selected = False
            self.refresh_tree()

        # ── Tabellen-Interaktion ───────────────────────────────────────────────

        def on_tree_click(self, event) -> Optional[str]:
            region = self.tree.identify("region", event.x, event.y)
            column = self.tree.identify_column(event.x)
            row    = self.tree.identify_row(event.y)
            if region == "tree" and column == "#0" and row:
                idx = int(row)
                if self.candidates[idx].status == SyncStatus.AENDERUNG:
                    self.candidates[idx].selected = not self.candidates[idx].selected
                    self.refresh_tree()
                    if self.tree.exists(row):
                        self.tree.selection_set(row)
                        self.tree.focus(row)
                    return "break"
            return None

        def on_tree_double_click(self, event) -> Optional[str]:
            region = self.tree.identify("region", event.x, event.y)
            column = self.tree.identify_column(event.x)
            row    = self.tree.identify_row(event.y)
            if region == "cell" and column == "#4" and row:
                self.start_edit_new_name(row)
                return "break"
            return None

        def edit_focused_new_name(self) -> None:
            row = self.tree.focus()
            if row:
                self.start_edit_new_name(row)

        def _destroy_edit_entry(self) -> None:
            if self._edit_entry is not None:
                try:
                    self._edit_entry.destroy()
                except Exception:
                    pass
                self._edit_entry = None

        def start_edit_new_name(self, row: str) -> None:
            idx = int(row)
            c = self.candidates[idx]
            if c.status != SyncStatus.AENDERUNG:
                return
            self._destroy_edit_entry()
            bbox = self.tree.bbox(row, "#4")
            if not bbox:
                return
            x, y, w, h = bbox
            p = self._p
            entry = tk.Entry(self.tree, font=TTK_BODY, bd=1, relief="solid",
                             bg=p["entry_bg"], fg=p["text"], insertbackground=p["text"])
            entry.insert(0, c.new_name)
            entry.select_range(0, "end")
            entry.focus_set()
            entry.place(x=x, y=y, width=w, height=h)
            self._edit_entry = entry
            # Dict statt Variable, damit commit/cancel die Flagge aus dem Closure heraus mutieren können.
            committed = {"done": False}

            def commit() -> None:
                if committed["done"]:
                    return
                committed["done"] = True
                value = entry.get().strip()
                self._destroy_edit_entry()
                if not value:
                    messagebox.showinfo("Hinweis", "Der neue Name darf nicht leer sein.")
                    return
                c.new_name = value
                c.selected = True
                self.refresh_tree()
                if self.tree.exists(row):
                    self.tree.selection_set(row)
                    self.tree.focus(row)
                self.update_details()
                self.status_var.set(f"Neuer Name geändert: {value}")

            def cancel() -> None:
                committed["done"] = True
                self._destroy_edit_entry()

            entry.bind("<Return>",   lambda _e: commit())
            entry.bind("<Escape>",   lambda _e: cancel())
            entry.bind("<FocusOut>", lambda _e: commit())

        def on_detail_new_name_changed(self, _event=None) -> None:
            selected = self.tree.selection()
            if not selected:
                return
            row = selected[0]
            try:
                c = self.candidates[int(row)]
            except (IndexError, ValueError):
                return
            if c.status != SyncStatus.AENDERUNG:
                return
            value = self.detail_vars["new"].get().strip()
            if not value:
                return
            c.new_name = value
            c.selected = True
            try:
                self.tree.set(row, "new", value)
                self.tree.item(row, text="✓")
                self.tree.item(row, tags=("selected_sync",))
            except Exception:
                pass
            self._update_summary()
            self.status_var.set(f"Neuer Name geändert: {value}")

        def toggle_selected_rows(self) -> None:
            selected = self.tree.selection()
            if not selected:
                return
            for iid in selected:
                idx = int(iid)
                if self.candidates[idx].status == SyncStatus.AENDERUNG:
                    self.candidates[idx].selected = not self.candidates[idx].selected
            self.refresh_tree()
            for iid in selected:
                if self.tree.exists(iid):
                    self.tree.selection_add(iid)
                    self.tree.focus(iid)

        # ── Clipboard ──────────────────────────────────────────────────────────

        def _clipboard_rows(self, iids: Sequence[str]) -> List[List[str]]:
            rows: List[List[str]] = [
                ["Sync", "Status", "GA", "Aktueller GPA-Name", "Neuer GPA-Name", "Datei im GPA"]]
            for iid in iids:
                try:
                    c = self.candidates[int(iid)]
                except (IndexError, ValueError):
                    continue
                rows.append(["ja" if c.selected else "nein",
                              c.status, c.group_address,
                              c.current_name, c.new_name, c.zip_path])
            return rows

        def _selected_iids_in_display_order(self) -> List[str]:
            selected = set(self.tree.selection())
            if not selected:
                focus = self.tree.focus()
                if focus:
                    selected.add(focus)
            ordered = [iid for iid in self.visible_iids if iid in selected]
            return ordered if ordered else list(selected)

        def _copy_rows_to_clipboard(self, iids: Sequence[str], mode: str = "excel") -> int:
            if not iids:
                self.status_var.set("Keine Zeile zum Kopieren ausgewählt.")
                return 0
            rows = self._clipboard_rows(iids)
            if mode == "csv":
                buf = io.StringIO()
                csv.writer(buf, delimiter=";", lineterminator="\n").writerows(rows)
                text, label = buf.getvalue(), "CSV"
            else:
                text = "\n".join(
                    "\t".join(str(cell).replace("\t", " ").replace("\n", " ") for cell in row)
                    for row in rows)
                label = "Excel"
            self.clipboard_clear()
            self.clipboard_append(text)
            count = max(0, len(rows) - 1)
            self.status_var.set(f"{count} Zeile(n) als {label}-Daten in die Zwischenablage kopiert.")
            return count

        def copy_selected_rows(self, event=None) -> str:
            self._copy_rows_to_clipboard(self._selected_iids_in_display_order(), mode="excel")
            return "break"

        def copy_selected_rows_excel(self) -> None:
            self._copy_rows_to_clipboard(self._selected_iids_in_display_order(), mode="excel")

        def copy_selected_rows_csv(self) -> None:
            self._copy_rows_to_clipboard(self._selected_iids_in_display_order(), mode="csv")

        def copy_visible_rows_excel(self) -> None:
            self._copy_rows_to_clipboard(list(self.visible_iids), mode="excel")

        def show_tree_context_menu(self, event) -> str:
            row = self.tree.identify_row(event.y)
            if row:
                if row not in self.tree.selection():
                    self.tree.selection_set(row)
                    self.tree.focus(row)
                self.update_details()
            try:
                self.tree_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.tree_menu.grab_release()
            return "break"

        # ── Details-Panel ──────────────────────────────────────────────────────

        def update_details(self) -> None:
            selected = self.tree.selection()
            if not selected:
                for var in self.detail_vars.values():
                    var.set("-")
                return
            c = self.candidates[int(selected[0])]
            self.detail_vars["status"].set(c.status)
            self.detail_vars["ga"].set(c.group_address)
            self.detail_vars["source"].set(c.source_field)
            self.detail_vars["old"].set(c.current_name)
            self.detail_vars["new"].set(c.new_name)

        # ── CSV-Export ─────────────────────────────────────────────────────────

        def save_csv(self) -> None:
            if not self.candidates:
                messagebox.showinfo("Hinweis", "Erst analysieren.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="gpa_sync_pruefliste.csv")
            if not path:
                return
            try:
                export_candidates_csv(self.candidates, Path(path))
                self.status_var.set(f"CSV gespeichert: {path}")
            except Exception as e:
                messagebox.showerror("Fehler beim CSV-Export", str(e))

        # ── Synchronisierung ───────────────────────────────────────────────────

        def _validate_selected_names(self) -> bool:
            selected_updates = {
                c.zip_path: c.new_name.strip()
                for c in self.candidates
                if c.selected and c.status == SyncStatus.AENDERUNG
            }
            if not selected_updates:
                messagebox.showinfo("Hinweis", "Keine Änderungen ausgewählt.")
                return False
            if any(not n for n in selected_updates.values()):
                messagebox.showerror("Ungültiger Name",
                                     "Mindestens ein ausgewählter neuer Name ist leer.")
                return False
            final_names: List[str] = []
            if self.datapoint_name_by_path:
                for path, current in self.datapoint_name_by_path.items():
                    final_names.append(selected_updates.get(path, current))
            else:
                final_names.extend(selected_updates.values())
            duplicates = sorted({n for n in final_names if final_names.count(n) > 1})
            if duplicates:
                messagebox.showerror("Doppelte Namen",
                    "Diese Zielnamen wären nach dem Speichern doppelt vorhanden:\n\n"
                    + "\n".join(duplicates[:20])
                    + ("\n..." if len(duplicates) > 20 else ""))
                return False
            return True

        def sync(self) -> None:
            selected = [c for c in self.candidates
                        if c.selected and c.status in (SyncStatus.AENDERUNG, SyncStatus.LEERZEICHEN)]
            if not self._validate_selected_names():
                return
            input_gpa = Path(self.gpa_var.get())
            out = filedialog.asksaveasfilename(
                defaultextension=".gpa",
                filetypes=[("GPA-Projekt", "*.gpa")],
                initialfile=input_gpa.stem + "_GA_SYNC.gpa")
            if not out:
                return
            if not self._ensure_password_if_needed(input_gpa):
                self.status_var.set("Synchronisierung abgebrochen: GPA-ZIP-Passwort nicht eingegeben.")
                return

            pwd = self._pwd()
            ets_path_str = self.ets_var.get().strip()
            self._set_busy(True)
            self.status_var.set("Synchronisierung läuft …")

            def worker() -> None:
                try:
                    changed = write_updated_gpa(input_gpa, Path(out), selected, pwd)
                    try:
                        ets_map: Dict[int, EtsGroupAddress] = {}
                        if ets_path_str:
                            try:
                                ets_map = parse_ets_ga_export(Path(ets_path_str))
                            except Exception:
                                ets_map = {}
                        out_datapoints = parse_gpa_datapoints(Path(out), pwd)
                        remaining = build_sync_candidates(out_datapoints, ets_map)
                        remaining_changes = sum(
                            1 for c in remaining
                            if c.status in (SyncStatus.AENDERUNG, SyncStatus.LEERZEICHEN))
                        check_text = (f"\n\nAbschlussprüfung: "
                                      f"{remaining_changes} eindeutige Unterschiede verbleiben.")
                    except Exception:
                        check_text = "\n\nAbschlussprüfung konnte nicht ausgeführt werden."
                    self.after(0, lambda: self._sync_done(changed, out, check_text))
                except Exception as exc:
                    self.after(0, lambda e=exc: self._sync_error(e))

            threading.Thread(target=worker, daemon=True).start()

        def _sync_done(self, changed: int, out: str, check_text: str) -> None:
            _log.info("Synchronisierung abgeschlossen: %d Datenpunkte geändert -> %s", changed, out)
            self._set_busy(False)
            self.status_var.set(f"Fertig: {changed} Datenpunkte geändert. Neue Datei: {out}")
            messagebox.showinfo("Fertig",
                f"{changed} Datenpunkte geändert.\n\nNeue GPA-Datei:\n{out}{check_text}"
                "\n\nBitte zuerst als Kopie im GPA öffnen und prüfen.")

        def _sync_error(self, error: Exception) -> None:
            _log.error("Synchronisierungsfehler: %s", error, exc_info=True)
            self._set_busy(False)
            self.status_var.set("Synchronisierung fehlgeschlagen.")
            messagebox.showerror("Fehler beim Synchronisieren", str(error))

    App().mainloop()
