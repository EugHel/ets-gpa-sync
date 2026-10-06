from __future__ import annotations

import csv
import io
import json
import os
import queue
import re
import threading
import webbrowser
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from ..core import (
    REFERENCE_FILTERS,
    DatapointReferences,
    EtsGroupAddress,
    EtsProjectPasswordRequired,
    GpaDatapoint,
    LogicReference,
    SyncCandidate,
    SyncStatus,
    TimerReference,
    VisuReference,
    build_partial_candidates,
    build_reference_map,
    build_sync_candidates,
    export_candidates_csv,
    format_ga_roles,
    matches_reference_filter,
    most_common_users,
    source_label,
    parse_ets_ga_export,
    parse_gpa_datapoints,
    summarize_sync_impact,
    write_updated_gpa,
)
from ..config import LICENSING_ENABLED, APP_VERSION, channel_type_display_name
from ..licensing import (
    LicenseManager, LicenseStatus, LicenseStorage, TrialManager,
    NullProvider, get_machine_id,
)
from ..log import get_logger
from .fonts import (get_fonts, TTK_BODY, TTK_BODY_BOLD, TTK_SMALL,
                    TTK_TABLE_HEADER, TTK_TABLE_BODY)

_log = get_logger("gui.app")

# ── Akzentfarben (identisch mit Legacy) ───────────────────────────────────────
ACCENT      = "#42a51b"
ACCENT_DARK = "#2f8612"

# ── Externe Links ─────────────────────────────────────────────────────────────
_LICENSE_URL = "https://github.com/EugHel/ets-gpa-sync"
_KOFI_URL    = "https://ko-fi.com/eughel"

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
        "conflict_fg":  "#f87171",
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
        "conflict_fg":  "#dc2626",
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

    def __init__(self, widget: tk.Widget, text, delay: int = 700) -> None:
        self._widget = widget
        self._get_text = text if callable(text) else lambda: text
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
        if self._win or not self._get_text():
            return
        x = self._widget.winfo_rootx() + 12
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._win = tk.Toplevel(self._widget)
        self._win.wm_overrideredirect(True)
        self._win.wm_geometry(f"+{x}+{y}")
        self._win.wm_attributes("-topmost", True)
        tk.Label(
            self._win, text=self._get_text(),
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


def _truncate_path_middle(path: str, max_chars: int = 45) -> str:
    """Kürzt einen langen Pfad in der Mitte: Anfang und Dateiname bleiben sichtbar."""
    if not path or len(path) <= max_chars:
        return path
    name = Path(path).name
    keep_start = max_chars - len(name) - 4  # 4 = len(" ... ")
    if keep_start < 4:
        return f"…{name}"
    return f"{path[:keep_start]} … {name}"


def run_gui() -> None:
    # ── TkinterDnD + CustomTkinter Integration ─────────────────────────────────
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD

        class _DndCTk(ctk.CTk, TkinterDnD.DnDWrapper):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                try:
                    self.TkdndVersion = TkinterDnD._require(self)
                except RuntimeError:
                    self.TkdndVersion = None

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
        # Verweise-Spalten der Tabelle (klickbar → Verwendungen-Popup).
        _REF_COLUMNS = ("visu", "logic", "timer")

        def __init__(self) -> None:
            super().__init__()
            # Zentrale Schrift-Stufen – direkt nach Tk-Init erstellen.
            # CTkFont skaliert automatisch mit Windows-DPI (kein manueller Eingriff).
            self._fonts = get_fonts()
            self.title("ETS GPA Sync")
            self.geometry("1420x820")
            self.minsize(1120, 600)

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
                "gpa":       tk.StringVar(value="–"),
                "ets":       tk.StringVar(value="–"),
                "diff":      tk.StringVar(value="0"),
                "selected":  tk.StringVar(value="0"),
                "conflicts": tk.StringVar(value="0"),
                # Nur GPA-Prüfansicht (ohne ETS):
                "used":      tk.StringVar(value="0"),
                "logic":     tk.StringVar(value="0"),
                "unused":    tk.StringVar(value="0"),
                "timer":     tk.StringVar(value="0"),
            }
            # True, wenn nur ein GPA-Projekt analysiert wurde (reine Prüfansicht).
            self._gpa_only = False
            self.datapoint_by_path: Dict[str, GpaDatapoint] = {}
            # Projekttypische Benutzer-Kombination; im Panel nur Abweichungen zeigen.
            self._default_users: tuple = ()
            self.candidates: List[SyncCandidate] = []
            self.datapoint_name_by_path: Dict[str, str] = {}
            # GPA-Verweise (Visu/Logik/Zeitschaltuhr) je Datenpunkt, im Analyse-Worker
            # vollständig aufgelöst – Tabelle, Filter, Panel, Popup, CSV und
            # Sync-Prüfung arbeiten nur auf diesen Daten (kein offenes ZIP-Handle).
            self.references: Dict[str, DatapointReferences] = {}
            self._ref_search_text: Dict[str, str] = {}
            self.ref_filter_mode: str = REFERENCE_FILTERS[0]
            # after()-Handle des Verweise-Debounce im Eigenschaften-Panel.
            self._xref_debounce_id: Optional[str] = None
            self.visible_iids: List[str] = []
            self._edit_entry: Optional[tk.Entry] = None
            self.sort_column: Optional[str] = None
            self.sort_reverse = False
            self.heading_titles = {
                "#0":    "Sync",
                "status":"Status",
                "ga":    "GA",
                "room":  "Raum",
                "old":   "Aktueller GPA-Name",
                "new":   "Neuer GPA-Name aus ETS",
                "visu":  "Visu",
                "logic": "Logik",
                "timer": "Uhr",
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
                            rowheight=30,
                            font=TTK_TABLE_BODY,
                            background=p["row_even"],
                            fieldbackground=p["row_even"],
                            foreground=p["text"],
                            bordercolor=p["border"],
                            borderwidth=0)
            _sep_color = p["border"]
            style.configure("Treeview.Heading",
                            font=TTK_TABLE_HEADER,
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
                self.tree.tag_configure("conflict",      foreground=p["conflict_fg"])

        def _toolbar_bg(self) -> str:
            """Exakte Hintergrundfarbe der Toolbar (CTk fg_color gray88 / gray14)."""
            return "#e0e0e0" if self._theme_mode == "light" else "#242424"

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
            if hasattr(self, "_logo_canvas") and self._logo_canvas is not None:
                self._logo_canvas.configure(bg=self._toolbar_bg())
            if hasattr(self, "_logo_label"):
                self._logo_label.configure(bg=self._toolbar_bg())
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
                self._logo_image = tk.PhotoImage(file=str(_icon_png))
                # tk.Label folgt dem CTk-Theme nicht von selbst → Hintergrund wird in
                # _refresh_legacy_widgets nachgezogen (sonst dunkles Kästchen im hellen Modus).
                self._logo_label = tk.Label(toolbar, image=self._logo_image, text="", width=66,
                                            borderwidth=0, highlightthickness=0,
                                            bg=self._toolbar_bg())
                self._logo_label.grid(row=0, column=0, padx=(12, 6), pady=6, sticky="w")
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

            ctk.CTkLabel(toolbar, text="ETS GPA Sync",
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

        def _center_dialog(self, title: str) -> None:
            """Zentriert das nächste messagebox-Fenster auf dem Tool-Fenster.

            Standard-messagebox kennt keine eigene Positionierung; daher wird
            das frisch erzeugte Toplevel kurz nach dem Aufruf per after()
            anhand seines Titels gesucht und mittig positioniert.
            """
            def _do():
                for w in self.winfo_children():
                    if isinstance(w, tk.Toplevel) and w.title() == title:
                        self.update_idletasks()
                        x = self.winfo_x() + (self.winfo_width() // 2) - (w.winfo_width() // 2)
                        y = self.winfo_y() + (self.winfo_height() // 2) - (w.winfo_height() // 2)
                        w.geometry(f"+{x}+{y}")
                        break
            self.after(10, _do)

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
                         font=self._fonts["subheader"],
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

            _path_display = tk.StringVar()
            var.trace_add("write", lambda *_: _path_display.set(
                _truncate_path_middle(var.get())))
            _path_lbl = ctk.CTkLabel(card, textvariable=_path_display,
                                     text_color=("gray35", "gray65"),
                                     font=self._fonts["body"],
                                     anchor="w")
            _path_lbl.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
            _Tooltip(_path_lbl, lambda v=var: v.get() or "")

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

        # Anzahl KPI-Plätze; je nach Modus werden 5 oder 6 davon gezeigt.
        _KPI_SLOTS = 6

        def _build_kpi_row(self, parent) -> None:
            """Baut die KPI-Plätze. Inhalt und Klickbarkeit setzt _render_kpis je Modus."""
            row = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
            row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
            self._kpi_row = row
            self._kpi_canvases: List[tk.Canvas] = []
            self._kpi_slots: List[Dict] = []
            self._kpi_hover: Optional[int] = None
            for col in range(self._KPI_SLOTS):
                card = self._card(row, 0, col, padx=(0, 8))
                card.columnconfigure(1, weight=1)
                # Feste Symbole für GPA/ETS (Canvas), sonst ein Text-Symbol.
                canvas = None
                if col == 0:
                    canvas = self._make_gpa_kpi_icon(card)
                    self._gpa_kpi_canvas = canvas
                elif col == 1:
                    canvas = self._make_ets_kpi_icon(card)
                if canvas is not None:
                    self._kpi_canvases.append(canvas)
                    canvas.grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="w")
                icon = ctk.CTkLabel(card, text="", font=self._fonts["large"], width=44)
                title = ctk.CTkLabel(card, text="", font=self._fonts["body"], anchor="w")
                title.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=(8, 0))
                value = ctk.CTkLabel(card, text="", font=self._fonts["kpi"], anchor="w")
                value.grid(row=1, column=1, sticky="w", padx=(0, 10), pady=(0, 8))
                for w in [card, icon, title, value] + ([canvas] if canvas is not None else []):
                    w.bind("<Button-1>", lambda _e, i=col: self._on_kpi_click(i), add="+")
                    w.bind("<Enter>", lambda _e, i=col: self._on_kpi_hover(i), add="+")
                    w.bind("<Leave>", lambda _e, i=col: self._on_kpi_hover(None), add="+")
                # state="init": erzwingt beim ersten _render_kpis das Einrichten (auch
                # das Ausblenden unbenutzter Plätze).
                self._kpi_slots.append(dict(card=card, canvas=canvas, icon=icon,
                                            title=title, value=value, spec=None, state="init"))
                _Tooltip(card, lambda i=col: self._kpi_tooltip(i))
            self._render_kpis()

        def _kpi_specs(self) -> List[Dict]:
            """KPI-Karten für den aktuellen Modus.

            Jede Karte: title, var (kpi_vars-Schlüssel), icon ("gpa"/"ets" = Canvas,
            sonst Text-Symbol), color und mode (Filter beim Klick oder None).
            """
            conflicts = int(self.kpi_vars["conflicts"].get() or 0)
            conflict = dict(title="Konflikte", var="conflicts",
                            icon="❌" if conflicts else "✅",
                            color="#dc2626" if conflicts else "#16a34a",
                            mode=self._CONFLICT_FILTER if conflicts else None)
            reset = (REFERENCE_FILTERS[0]
                     if self._gpa_only or self.ref_filter_mode != REFERENCE_FILTERS[0] else None)
            gpa = dict(title="GPA-Datenpunkte", var="gpa", icon="gpa", color="", mode=reset)
            if not self._gpa_only:
                return [gpa,
                        dict(title="ETS-Adressen", var="ets", icon="ets", color="", mode=None),
                        dict(title="Unterschiede", var="diff", icon="⚠", color="#f59e0b", mode=None),
                        dict(title="Ausgewählt", var="selected", icon="✓", color="#16a34a", mode=None),
                        conflict]
            has_logic, has_timer = self._project_has("logic"), self._project_has("timer")
            logic = dict(title="In Logik", var="logic", icon="⚙", color="#0ea5e9", mode="In Logik")
            timer = dict(title="Mit Zeitschaltuhr", var="timer", icon="⏰", color="#a855f7",
                         mode="Mit Zeitschaltuhr")
            specs = [gpa,
                     dict(title="Verwendet", var="used", icon="🔗", color="#16a34a", mode="Verwendet")]
            if has_logic or not has_timer:
                specs.append(logic)
            specs.append(dict(title="Ungenutzt", var="unused", icon="○", color="#f59e0b",
                              mode="Ungenutzt"))
            if has_timer:
                specs.append(timer)
            specs.append(conflict)
            return specs

        def _render_kpis(self) -> None:
            """Überträgt _kpi_specs auf die KPI-Plätze inkl. Klick-Optik und Aktiv-Markierung.

            Jeder Platz wird nur neu konfiguriert, wenn sich sein Zustand geändert hat –
            wiederholtes Umkonfigurieren (bei jeder Tabellenaktualisierung) ließ die
            Karten sonst sichtbar flackern.
            """
            if not hasattr(self, "_kpi_slots"):
                return
            specs = self._kpi_specs()
            for i, slot in enumerate(self._kpi_slots):
                spec = specs[i] if i < len(specs) else None
                slot["spec"] = spec
                clickable = spec is not None and spec["mode"] is not None
                active = (clickable and spec["mode"] != REFERENCE_FILTERS[0]
                          and spec["mode"] == self.ref_filter_mode)
                state = (None if spec is None else
                         (tuple(sorted(spec.items())), active, i == len(specs) - 1))
                if slot.get("state") == state:
                    continue
                slot["state"] = state
                card = slot["card"]
                if spec is None:
                    card.grid_remove()
                    self._kpi_row.columnconfigure(i, weight=0, uniform="")
                    continue
                self._kpi_row.columnconfigure(i, weight=1, uniform="kpi")
                last = i == len(specs) - 1
                card.grid(row=0, column=i, sticky="nsew", padx=(0, 0) if last else (0, 8))
                # Symbol: Canvas nur, wenn der Platz genau dieses Symbol zeigen soll.
                canvas_key = {0: "gpa", 1: "ets"}.get(i)
                if slot["canvas"] is not None and spec["icon"] == canvas_key:
                    slot["icon"].grid_remove()
                    slot["canvas"].grid()
                else:
                    if slot["canvas"] is not None:
                        slot["canvas"].grid_remove()
                    slot["icon"].configure(text=spec["icon"], text_color=spec["color"] or None)
                    slot["icon"].grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="w")
                color = (ACCENT_DARK, ACCENT) if active else ("gray10", "gray90")
                # Klickbarkeit: Hand-Cursor + grüner Rahmen beim Überfahren/aktiv.
                slot["title"].configure(text=spec["title"], text_color=color)
                slot["value"].configure(textvariable=self.kpi_vars[spec["var"]], text_color=color)
                slot["active"] = active
                self._paint_kpi_border(i)
                cursor = "hand2" if clickable else ""
                for key in ("card", "icon", "title", "value", "canvas"):
                    widget = slot[key]
                    if widget is not None:
                        try:
                            widget.configure(cursor=cursor)
                        except Exception:  # pragma: no cover - nicht jedes Widget kennt cursor
                            pass

        def _paint_kpi_border(self, index: int) -> None:
            slot = self._kpi_slots[index]
            spec = slot.get("spec")
            clickable = spec is not None and spec["mode"] is not None
            highlight = slot.get("active") or (clickable and self._kpi_hover == index)
            want = (2, (ACCENT_DARK, ACCENT)) if highlight else (1, ("gray78", "gray28"))
            if slot.get("border") != want:
                slot["border"] = want
                slot["card"].configure(border_width=want[0], border_color=want[1])

        def _kpi_tooltip(self, index: int) -> str:
            spec = self._kpi_slots[index]["spec"] if hasattr(self, "_kpi_slots") else None
            if not spec or spec["mode"] is None:
                return ""
            if spec["mode"] == REFERENCE_FILTERS[0]:
                return "Klicken: Filter aufheben und alle Datenpunkte zeigen."
            if spec["mode"] == self.ref_filter_mode:
                return "Filter aktiv – erneut klicken zeigt wieder alle Zeilen."
            return f"Klicken: Tabelle auf „{spec['title']}“ filtern."

        def _on_kpi_hover(self, index: Optional[int]) -> None:
            """Hover-Rahmen. Beim Wechsel zwischen Karte und ihren Beschriftungen feuert
            Tk Leave/Enter – ein Leave, bei dem der Mauszeiger noch in derselben Karte
            steht, wird ignoriert (sonst flackert der Rahmen)."""
            if index is None and self._kpi_hover is not None:
                card = self._kpi_slots[self._kpi_hover]["card"]
                under = self.winfo_containing(*self.winfo_pointerxy())
                while under is not None:
                    if under is card:
                        return
                    under = under.master
            if self._kpi_hover == index:
                return
            previous, self._kpi_hover = self._kpi_hover, index
            for i in (previous, index):
                if i is not None:
                    self._paint_kpi_border(i)

        def _on_kpi_click(self, index: int) -> None:
            """Klickbare KPI-Karten filtern die Tabelle; erneuter Klick hebt den Filter auf."""
            spec = self._kpi_slots[index]["spec"] if index < len(self._kpi_slots) else None
            if not spec or spec["mode"] is None:
                return
            mode = spec["mode"]
            if mode == REFERENCE_FILTERS[0] or self.ref_filter_mode == mode:
                self._set_row_filter(REFERENCE_FILTERS[0])
            else:
                self._set_row_filter(mode)

        def _build_center_panel(self, parent) -> None:
            center = self._card(parent, 2)
            center.columnconfigure(0, weight=1)
            center.rowconfigure(2, weight=1)

            # Titelzeile: Titel links, rechts aktiver Filter (klickbar zum Aufheben)
            # und Zeilenzähler. Gefiltert wird über die KPI-Karten oben.
            head = ctk.CTkFrame(center, corner_radius=0, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", padx=16, pady=(10, 6))
            head.columnconfigure(1, weight=1)
            self._center_title = ctk.CTkLabel(head, text="Datenpunkte – Änderungen",
                                              font=self._fonts["normal"],
                                              anchor="w")
            self._center_title.grid(row=0, column=0, sticky="w")
            self._filter_chip = ctk.CTkButton(
                head, text="", height=26, corner_radius=13, width=10,
                fg_color=(ACCENT, ACCENT_DARK), hover_color=(ACCENT_DARK, "#256b0e"),
                text_color="white", font=self._fonts["body"],
                command=self._clear_row_filter)
            self.table_count_var = tk.StringVar(value="")
            ctk.CTkLabel(head, textvariable=self.table_count_var,
                         font=self._fonts["body"],
                         text_color=("gray30", "gray65")).grid(
                row=0, column=3, sticky="e", padx=(10, 0))

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
            self._search_clear.bind("<Button-1>", lambda _: self._clear_search())
            self._search_clear.bind("<Enter>",
                lambda _: self._search_clear.configure(text_color=("gray15", "gray90")))
            self._search_clear.bind("<Leave>",
                lambda _: self._search_clear.configure(text_color=("gray40", "gray65")))

            # Bewusst OHNE textvariable: CTkEntry zeigt mit textvariable keinen
            # Platzhalter an. Der Text wird per KeyRelease in filter_var gespiegelt.
            self.search_entry = ctk.CTkEntry(
                self._search_frame,
                placeholder_text="Suchen: Name, GA, Raum, Ansicht, Logikseite …",
                font=self._fonts["body"],
                border_width=0, fg_color="transparent")
            self.search_entry.grid(row=0, column=1, sticky="ew", padx=(2, 4), pady=2)
            def _on_search_key(_e=None) -> None:
                text = self.search_entry.get()
                if text != self.filter_var.get():
                    self.filter_var.set(text)

            self.search_entry.bind("<KeyRelease>", _on_search_key)

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

            cols = ("status", "ga", "room", "old", "new") + self._REF_COLUMNS
            self.tree = ttk.Treeview(table_frame, columns=cols,
                                     show="tree headings", selectmode="extended")
            self._refresh_headings()
            self.tree.column("#0",     width=70,  minwidth=66,  anchor="center", stretch=False)
            self.tree.column("status", width=120, minwidth=100, anchor="w",      stretch=False)
            self.tree.column("ga",     width=130, minwidth=90,  anchor="w",      stretch=False)
            # Startbreiten so gewählt, dass alle Spalten inkl. Visu/Logik/Uhr bei der
            # Standard-Fenstergröße sichtbar sind; die Text-Spalten wachsen mit.
            # Welche Spalten sichtbar sind, steuert _apply_view_mode (displaycolumns).
            self.tree.column("room",   width=170, minwidth=110, anchor="w",      stretch=True)
            self.tree.column("old",    width=200, minwidth=140, anchor="w",      stretch=True)
            self.tree.column("new",    width=200, minwidth=140, anchor="w",      stretch=True)
            for col in self._REF_COLUMNS:
                self.tree.column(col, width=66, minwidth=56, anchor="center", stretch=False)
            self.tree.grid(row=0, column=0, sticky="nsew")
            self.tree.bind("<Configure>", self._fit_columns, add="+")
            self.tree.bind("<Configure>",
                           lambda _e: getattr(self, "_guide_on", False) and self._place_start_guide(),
                           add="+")
            # Platzhalter über der leeren Tabelle (Farbe = Zeilenhintergrund row_even).
            self._empty_hint = ctk.CTkLabel(
                table_frame, text="", font=self._fonts["body"], justify="center",
                text_color=("gray35", "gray65"), fg_color=("#ffffff", "#2b2b2b"))
            self._start_guide = self._build_start_guide(table_frame)

            yscroll = ctk.CTkScrollbar(table_frame, command=self.tree.yview)
            self.tree.configure(yscrollcommand=yscroll.set)
            yscroll.grid(row=0, column=1, sticky="ns")

            self.tree.bind("<Button-1>",       self.on_tree_click)
            self.tree.bind("<Motion>",         self._on_tree_motion)
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
            right.rowconfigure(1, weight=1)
            right.grid_propagate(False)
            right.configure(width=300)

            ctk.CTkLabel(right, text="Eigenschaften",
                         font=self._fonts["subheader"],
                         anchor="w").grid(row=0, column=0, sticky="w",
                                          padx=16, pady=(14, 4))

            form = ctk.CTkFrame(right, corner_radius=0, fg_color="transparent")
            form.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
            form.columnconfigure(0, weight=1)


            # Feld-Widgets je Name, damit die ETS-Felder in der GPA-Prüfansicht
            # ausgeblendet werden können (_apply_view_mode).
            self._detail_widgets: Dict[str, tuple] = {}

            def add_field(label: str, var_name: str, readonly: bool = True,
                          row: int = 0) -> ctk.CTkEntry:
                label_widget = ctk.CTkLabel(form, text=label, text_color=("gray30", "gray65"),
                                            font=self._fonts["property_label"], anchor="w")
                label_widget.grid(row=row, column=0, sticky="w", pady=(6, 1))
                entry = ctk.CTkEntry(
                    form, textvariable=self.detail_vars[var_name],
                    state="readonly" if readonly else "normal",
                    font=self._fonts["property_label"],
                    text_color=("#1a1a1a", "#e8e8e8"))
                entry.grid(row=row + 1, column=0, sticky="ew")
                self._detail_widgets[var_name] = (label_widget, entry)
                return entry

            add_field("Status",               "status", row=1)
            add_field("Gruppenadresse",        "ga",     row=3)
            # Alle Adressen des Datenpunkts nach Rolle (Senden/Status/Hören).
            self.detail_ga_roles = ctk.CTkLabel(
                form, text="", font=self._fonts["detail_sub"], justify="left",
                text_color=("gray30", "gray70"), anchor="w", wraplength=260, height=20)
            self.detail_ga_roles.grid(row=5, column=0, sticky="ew", pady=(2, 0))
            add_field("Quelle",                "source", row=6)
            add_field("Aktueller GPA-Name",      "old",    row=8)
            self.detail_new_entry = add_field("Neuer GPA-Name aus ETS (editierbar)", "new",
                                              readonly=False, row=10)
            self.detail_new_entry.bind("<KeyRelease>", self.on_detail_new_name_changed)
            self.detail_new_entry.bind("<Return>",     self.on_detail_new_name_changed)

            # Verweise: gegliederte Liste (Visu / Logik / Zeitschaltuhr) in einem
            # scrollbaren Bereich, der die Resthöhe des Panels füllt. Aufbau bei
            # jedem Zeilenwechsel (_populate_detail_xrefs), gleiche Optik wie das Popup.
            form.rowconfigure(13, weight=1)
            self.detail_xref_header = ctk.CTkLabel(
                form, text="GPA-Verweise", text_color=("gray30", "gray65"),
                font=self._fonts["property_label"], anchor="w")
            self.detail_xref_header.grid(row=12, column=0, sticky="w", pady=(6, 1))
            self.detail_xref_frame = ctk.CTkScrollableFrame(
                form, fg_color="transparent", corner_radius=0)
            self.detail_xref_frame.grid(row=13, column=0, sticky="nsew")
            self.detail_xref_frame.columnconfigure(0, weight=1)
            self.detail_xref_frame._parent_canvas.bind(
                "<Configure>", lambda _e: self.after_idle(self._update_xref_scrollbar), add="+")
            # Startzustand: Hinweis statt leerer Fläche mit Scrollbalken.
            self.after(150, self.update_details)
            self.after(150, self._update_empty_hint)

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
                footer, text=APP_VERSION,
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
              "Filtert die Tabelle in Echtzeit.\nDurchsucht GA, Namen, Status, Raum,\n"
              "Visu-Ansichten und Logikseiten.")
            T(self.sync_button,
              "Erstellt eine neue GPA-Datei mit den ausgewählten\nNamens-Änderungen. Die Originaldatei bleibt unverändert.")
            T(self._theme_switch,
              "Design zwischen Hell und Dunkel wechseln.")

        def _setup_drop_targets(self) -> None:
            if not DND_AVAILABLE or not getattr(self, 'TkdndVersion', None):
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
                self._center_dialog("Nicht erkannt")
                messagebox.showinfo("Nicht erkannt",
                                    "Bitte eine .gpa-, .xml- oder .knxproj-Datei ablegen.")

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
            for col in ("#0", "status", "ga", "room", "old", "new") + self._REF_COLUMNS:
                try:
                    anchor = "center" if col in self._REF_COLUMNS else "w"
                    self.tree.heading(col, text=self._heading_text(col), anchor=anchor,
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
                if column == "room":
                    # Ohne Raum ans Ende (bei aufsteigender Sortierung).
                    room = self._room_text(c)
                    return (room == "", room.lower(), c.current_name.lower())
                if column == "old":
                    return (c.current_name.lower(), c.group_address_value)
                if column == "new":
                    return (c.new_name.lower(), c.group_address_value)
                if column in self._REF_COLUMNS:
                    # "nicht anwendbar" (kein Datenpunkt) ans Ende schieben (-1).
                    return (self._ref_count(c, column), c.current_name.lower())
                return (c.group_address_value, c.current_name.lower())

            self.candidates.sort(key=key, reverse=self.sort_reverse)
            self.refresh_tree()
            self._refresh_headings()

        # ── Hilfe ──────────────────────────────────────────────────────────────

        def show_help(self) -> None:
            self._center_dialog("Hilfe – ETS GPA Sync")
            messagebox.showinfo("Hilfe – ETS GPA Sync",
                'Zweck:\n'
                'Dieses Tool übernimmt Gruppenadressnamen aus einem ETS-Export in ein GPA-Projekt. '
                'Synchronisiert wird nur in Richtung ETS → GPA.\n\n'
                'Ablauf:\n'
                '1. GPA-Projekt (.gpa) ablegen oder auswählen.\n'
                '2. ETS-Gruppenadressen-Export (.xml) oder ETS-Projekt (.knxproj) ablegen oder auswählen.\n'
                '3. Auf „Analysieren“ klicken.\n'
                '4. Änderungen prüfen und bei Bedarf einzelne Zeilen abwählen.\n'
                '5. Mit „Synchronisieren“ eine neue GPA-Datei erzeugen.\n\n'
                'Wichtig:\n'
                'Das Originalprojekt wird nicht verändert. Im GPA-Projekt wird nur der sichtbare '
                'Datenpunktname geändert. LogicalName und Gruppenadressen bleiben unverändert.\n\n'
                'Hinweise:\n'
                '• Mit Doppelklick oder F2 kann der neue GPA-Name direkt in der Liste bearbeitet werden.\n'
                '• Mit Rechtsklick oder Strg+C können markierte Zeilen nach Excel kopiert werden.\n'
                '• Wenn nur eine Datei geladen ist, wird trotzdem eine reine Kontrollliste angezeigt.\n'
                '• .knxproj-Dateien können ein ETS-Projektpasswort benötigen.\n'
                '• Reine Leerzeichen-Unterschiede werden als „Leerzeichen“ markiert.\n'
                '• GPA-Adressen ohne Treffer im ETS-Export werden als „Nicht in ETS“ angezeigt.\n'
                '• Mehrere GPA-Datenpunkte mit identischer Gruppenadresse werden als „Adress-Konflikt“ '
                'angezeigt und nicht automatisch umbenannt – bitte prüfen.\n\n'
                'GPA-Verweise:\n'
                'Die Spalten „Visu“, „Logik“ und „Uhr“ zeigen, wo ein Datenpunkt im GPA-Projekt '
                'verwendet wird: in Visu-Ansichten, als Baustein im Logikeditor oder durch eine '
                'Zeitschaltuhr. Ein Klick auf eine Zahl öffnet die Details (Standort, Logikseite, '
                'Schaltzeiten, sichtbar für welche Benutzer). Die Spalte „Raum“ zeigt den Standort '
                'der Visu-Ansicht. Mit dem Filter „Ungenutzt“ findest du Datenpunkte, die nirgends '
                'verwendet werden.\n\n'
                'GPA-Prüfansicht:\n'
                'Wird nur ein GPA-Projekt analysiert, blendet das Tool die ETS-Spalten aus. Die '
                'Kennzahlen „Verwendet“, „In Logik“ und „Ungenutzt“ filtern per Klick die Tabelle.')

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
            conflicts = sum(1 for c in self.candidates
                            if c.status == SyncStatus.ADRESSKONFLIKT)
            self.kpi_vars["diff"].set(str(total))
            self.kpi_vars["selected"].set(str(selected))
            self.kpi_vars["conflicts"].set(str(conflicts))
            refs = self.references.values()
            self.kpi_vars["used"].set(str(sum(1 for r in refs if not r.is_unused)))
            self.kpi_vars["logic"].set(str(sum(1 for r in refs if r.logic)))
            self.kpi_vars["unused"].set(str(sum(1 for r in refs if r.is_unused)))
            self.kpi_vars["timer"].set(str(sum(1 for r in refs if r.timers)))
            if hasattr(self, "table_count_var"):
                self.table_count_var.set(f"Zeilen: {visible} von {total}")
            self._render_kpis()

        # ── Ansichtsmodus: ETS-Vergleich vs. GPA-Prüfansicht ───────────────────

        def _show_detail_fields(self, has_selection: bool) -> None:
            """Panel-Felder ein-/ausblenden: ohne Auswahl nur der Hinweis im Verweise-
            Bereich; "Neuer Name" nur im Vergleich; "Status" in der Prüfansicht nur bei
            Adress-Konflikten (sonst stünde überall "Nur GPA")."""
            conflicts = any(c.status == SyncStatus.ADRESSKONFLIKT for c in self.candidates)
            for name, widgets in self._detail_widgets.items():
                hide = (not has_selection
                        or (name == "new" and self._gpa_only)
                        or (name == "status" and self._gpa_only and not conflicts))
                for w in widgets:
                    w.grid_remove() if hide else w.grid()

        def _project_has(self, kind: str) -> bool:
            """Ob das analysierte GPA-Projekt überhaupt Logik-/Uhr-Verweise enthält."""
            attr = {"logic": "logic", "timer": "timers"}[kind]
            return any(getattr(r, attr) for r in self.references.values())

        def _apply_view_mode(self) -> None:
            """Blendet je nach Modus Spalten, Kennzahlen, Knöpfe und Felder ein/aus.

            GPA-Prüfansicht (nur GPA geladen): keine ETS-Spalten, kein Sync, KPIs
            Verwendet / In Logik / Ungenutzt (anklickbar als Filter). Logik- und
            Uhr-Spalte nur, wenn das Projekt solche Verweise enthält.
            """
            gpa_only = self._gpa_only
            has_refs = bool(self.references)
            conflicts = any(c.status == SyncStatus.ADRESSKONFLIKT for c in self.candidates)

            cols: List[str] = []
            if not gpa_only or conflicts:
                cols.append("status")
            cols.append("ga")
            if has_refs:
                cols.append("room")
            cols.append("old")
            if not gpa_only:
                cols.append("new")
            if has_refs:
                cols.append("visu")
                if self._project_has("logic"):
                    cols.append("logic")
                if self._project_has("timer"):
                    cols.append("timer")
            self.tree.configure(displaycolumns=cols,
                                show="headings" if gpa_only else "tree headings")

            self._center_title.configure(
                text="Datenpunkte" if gpa_only else "Datenpunkte – Änderungen")
            for name in ("select_all_button", "deselect_all_button", "sync_button"):
                widget = getattr(self, name)
                widget.grid_remove() if gpa_only else widget.grid()
            self._show_detail_fields(bool(self.tree.selection()))
            self.after_idle(self._fit_columns)

            self._render_kpis()

        # Gewichte der mitwachsenden Text-Spalten beim Verteilen der Tabellenbreite.
        _STRETCH_WEIGHTS = {"room": 1.0, "old": 1.4, "new": 1.4}

        def _fit_columns(self, _event=None) -> None:
            """Verteilt die freie Tabellenbreite auf die sichtbaren Text-Spalten.

            ttk.Treeview passt die Spalten nach einem Wechsel von displaycolumns nicht
            von selbst an – ohne das bliebe rechts Leerraum bzw. Spalten würden abgeschnitten.
            """
            if not hasattr(self, "tree"):
                return
            total = self.tree.winfo_width()
            if total <= 1:
                return
            shown = tuple(self.tree["displaycolumns"])
            if not shown or shown == ("#all",):
                shown = tuple(self.tree["columns"])
            stretch = [c for c in shown if c in self._STRETCH_WEIGHTS]
            fixed = sum(int(self.tree.column(c, "width")) for c in shown if c not in stretch)
            if "tree" in str(self.tree.cget("show")):
                fixed += int(self.tree.column("#0", "width"))
            free = total - fixed - 4
            weight_sum = sum(self._STRETCH_WEIGHTS[c] for c in stretch)
            if not stretch or free <= 0:
                return
            for c in stretch:
                width = int(free * self._STRETCH_WEIGHTS[c] / weight_sum)
                self.tree.column(c, width=max(int(self.tree.column(c, "minwidth")), width))

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
                self._center_dialog("Hinweis")
                messagebox.showwarning("Hinweis",
                    "Bitte mindestens eine GPA-Datei oder einen ETS-Export auswählen.")
                return
            if gpa is not None and not gpa.exists():
                self._center_dialog("Fehler")
                messagebox.showerror("Fehler", "GPA-Datei nicht gefunden. Bitte erneut auswählen.")
                return
            if ets is not None and not ets.exists():
                self._center_dialog("Fehler")
                messagebox.showerror("Fehler", "ETS-Datei nicht gefunden. Bitte erneut auswählen.")
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
                    # GPA-Verweise (Visu/Logik/Zeitschaltuhr) aller Datenpunkte einmal
                    # vollständig auflösen – danach kein offenes ZIP-Handle mehr nötig.
                    references: Dict[str, DatapointReferences] = {}
                    if gpa is not None and datapoints:
                        try:
                            references = build_reference_map(gpa, datapoints, gpa_pwd)
                        except Exception as exc:  # pragma: no cover - defensiv
                            _log.warning("GPA-Verweise nicht auflösbar: %s", exc)
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
                    self.after(0, lambda: self._analyze_done(
                        datapoints, ets_map, candidates, references))
                except Exception as exc:
                    self.after(0, lambda e=exc: self._analyze_error(e))

            threading.Thread(target=worker, daemon=True).start()

        def _analyze_cancelled(self, message: str) -> None:
            self._set_busy(False)
            self.status_var.set(message)

        def _analyze_done(self, datapoints: List[GpaDatapoint],
                          ets_map: Dict[int, EtsGroupAddress],
                          candidates: List[SyncCandidate],
                          references: Optional[Dict[str, DatapointReferences]] = None) -> None:
            _log.info("Analyse abgeschlossen: %d Datenpunkte, %d ETS-GAs, %d Kandidaten",
                      len(datapoints), len(ets_map), len(candidates))
            self.candidates = candidates
            self.datapoint_name_by_path = {dp.zip_path: dp.entity_name for dp in datapoints}
            self.datapoint_by_path = {dp.zip_path: dp for dp in datapoints}
            self.references = references or {}
            self._gpa_only = bool(datapoints) and not ets_map
            self._default_users = most_common_users(self.references)
            # Suchtext je Datenpunkt: Ansichten, Standorte, Logikseiten, Zeitschaltuhren.
            self._ref_search_text = {
                path: refs.summary_text().lower() for path, refs in self.references.items()}
            self.sort_column = "ga"
            self.sort_reverse = False
            self._set_busy(False)
            # Filter zurücksetzen, falls er im neuen Projekt nicht mehr angeboten wird.
            self.ref_filter_mode = REFERENCE_FILTERS[0]
            self._apply_view_mode()
            self._update_filter_ui()
            self.refresh_tree()
            self._update_summary(len(datapoints), len(ets_map))
            unused = sum(1 for r in self.references.values() if r.is_unused)
            in_logic = sum(1 for r in self.references.values() if r.logic)
            ref_parts = []
            if self.references:
                if in_logic:
                    ref_parts.append(f"{in_logic} in Logik")
                timers = sum(1 for r in self.references.values() if r.timers)
                if timers:
                    ref_parts.append(f"{timers} mit Zeitschaltuhr")
                ref_parts.append(f"{unused} ungenutzt")
            ref_info = "".join(f" · {p}" for p in ref_parts)
            if datapoints and ets_map:
                self.status_var.set(
                    f"Vergleich: {len(datapoints)} GPA-Datenpunkte · {len(ets_map)} ETS-Adressen · "
                    f"{len(candidates)} {'Unterschied' if len(candidates) == 1 else 'Unterschiede'}"
                    + ref_info)
            elif datapoints:
                self.status_var.set(
                    f"GPA-Prüfansicht: {len(datapoints)} Datenpunkte" + ref_info
                    + " – für den Namensabgleich zusätzlich eine ETS-Datei laden.")
            else:
                self.status_var.set(
                    f"ETS: {len(ets_map)} Gruppenadressen – für den Abgleich zusätzlich "
                    "ein GPA-Projekt laden.")

        def _analyze_error(self, error: Exception) -> None:
            _log.error("Analysefehler: %s", error, exc_info=True)
            self._set_busy(False)
            self.status_var.set("Analyse fehlgeschlagen.")
            self._center_dialog("Fehler bei Analyse")
            messagebox.showerror("Fehler bei Analyse", str(error))

        # ── Filter ─────────────────────────────────────────────────────────────

        def clear_filter(self) -> None:
            self._clear_search()

        def _row_matches_filter(self, c: SyncCandidate, needle: str) -> bool:
            if self.ref_filter_mode == self._CONFLICT_FILTER:
                if c.status != SyncStatus.ADRESSKONFLIKT:
                    return False
            elif not matches_reference_filter(self._refs_for(c), self.ref_filter_mode):
                return False
            if not needle:
                return True
            haystack = " | ".join([c.status, c.group_address, c.source_field,
                                    c.current_name, c.new_name, c.zip_path,
                                    self._ref_search_text.get(c.zip_path, "")]).lower()
            return needle in haystack

        # ── GPA-Verweise: Hilfen ──────────────────────────────────────────────

        def _refs_for(self, c: SyncCandidate) -> Optional[DatapointReferences]:
            """Verweise einer Zeile, oder None wenn die Zeile keinen GPA-Datenpunkt hat."""
            if not c.zip_path:
                return None
            return self.references.get(c.zip_path)

        def _ref_count(self, c: SyncCandidate, column: str) -> int:
            """Anzahl Verweise für eine Verweise-Spalte; -1 = nicht anwendbar."""
            refs = self._refs_for(c)
            if refs is None:
                return -1
            return {"visu": len(refs.visu), "logic": len(refs.logic),
                    "timer": len(refs.timers)}.get(column, -1)

        def _room_text(self, c: SyncCandidate) -> str:
            refs = self._refs_for(c)
            return refs.room_label() if refs is not None else ""

        def _ref_cell_text(self, c: SyncCandidate, column: str) -> str:
            count = self._ref_count(c, column)
            if count < 0:
                return ""
            return self._as_link_text(str(count)) if count else "–"

        # Zusätzlicher Tabellenfilter (nur Adress-Konflikte), neben REFERENCE_FILTERS.
        _CONFLICT_FILTER = "Adress-Konflikte"

        def _set_row_filter(self, mode: str) -> None:
            """Setzt den Tabellenfilter (KPI-Klick) und aktualisiert Tabelle, KPIs und Chip."""
            self.ref_filter_mode = mode
            self.refresh_tree()
            self._update_filter_ui()

        def _clear_row_filter(self) -> None:
            self._set_row_filter(REFERENCE_FILTERS[0])

        def _update_filter_ui(self) -> None:
            """Zeigt den aktiven Filter als Chip „Filter: … ✕“ in der Titelzeile."""
            if not hasattr(self, "_filter_chip"):
                return
            if self.ref_filter_mode == REFERENCE_FILTERS[0]:
                self._filter_chip.grid_remove()
            else:
                self._filter_chip.configure(text=f"  Filter: {self.ref_filter_mode}   ✕  ")
                self._filter_chip.grid(row=0, column=2, sticky="e")
            self._render_kpis()

        def _clear_search(self) -> None:
            self.search_entry.delete(0, "end")
            self.filter_var.set("")
            self.focus_set()  # Platzhaltertext wieder anzeigen

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
                if c.status == SyncStatus.ADRESSKONFLIKT:
                    mark = "!"
                    tags.append("conflict")
                # Verweise: "N ↗" als Link-Optik (ttk.Treeview erlaubt keine
                # zellgenaue Schrift/Farbe) plus hand2-Cursor; 0 → "–", ohne
                # Datenpunkt leer. Keine Zeilenfärbung für ungenutzte Datenpunkte.
                ref_texts = tuple(self._ref_cell_text(c, col) for col in self._REF_COLUMNS)
                self.tree.insert("", "end", iid=iid, text=mark,
                                 values=(c.status, c.group_address, self._room_text(c),
                                         c.current_name, c.new_name) + ref_texts,
                                 tags=tuple(tags))
                self.visible_iids.append(iid)
                visible_counter += 1
            for iid in current_selection:
                if self.tree.exists(iid):
                    self.tree.selection_add(iid)
            self._update_summary()
            self.update_details()
            self._refresh_headings()
            self._update_empty_hint()
            if hasattr(self, "sync_button"):
                can_sync = any(c.selected and c.status == SyncStatus.AENDERUNG
                               for c in self.candidates)
                self.sync_button.configure(state="normal" if can_sync else "disabled")

        def _build_start_guide(self, parent) -> ctk.CTkFrame:
            """Kurzanleitung über der leeren Tabelle vor der ersten Analyse."""
            bg = ("#ffffff", "#2b2b2b")  # = Zeilenhintergrund der Tabelle
            guide = ctk.CTkFrame(parent, fg_color=bg, corner_radius=0)
            muted = ("gray35", "gray65")
            blocks = [
                ("🔍", "Nur GPA-Projekt laden  →  „Analysieren“",
                 "Prüfansicht: zeigt für jeden Datenpunkt, wo er verwendet wird (Visu-Ansicht "
                 "mit Raum, Logik, Zeitschaltuhr) und welche nirgends verwendet werden. "
                 "Am Projekt wird nichts verändert."),
                ("⇄", "GPA-Projekt + ETS-Datei laden  →  „Analysieren“  →  „Synchronisieren“",
                 "Namensabgleich: „Analysieren“ listet alle Datenpunkte, deren Name in der GPA "
                 "von der ETS abweicht. „Synchronisieren“ speichert daraus eine neue .gpa-Datei "
                 "mit den Namen aus der ETS – das Original bleibt unverändert."),
            ]
            self._guide_bodies: List[ctk.CTkLabel] = []
            for i, (icon, head, body) in enumerate(blocks):
                r = i * 2
                ctk.CTkLabel(guide, text=icon, font=self._fonts["large"], width=36,
                             text_color=(ACCENT_DARK, ACCENT), fg_color=bg).grid(
                    row=r, column=0, rowspan=2, sticky="n", padx=(0, 10))
                ctk.CTkLabel(guide, text=head, font=self._fonts["body_bold"], anchor="w",
                             fg_color=bg).grid(row=r, column=1, sticky="w")
                body_label = ctk.CTkLabel(guide, text=body, font=self._fonts["body"],
                                          justify="left", anchor="w", wraplength=560,
                                          text_color=muted, fg_color=bg)
                body_label.grid(row=r + 1, column=1, sticky="w", pady=(0, 12))
                self._guide_bodies.append(body_label)
            self._guide_footer = ctk.CTkLabel(
                guide, text="Dateien oben ablegen oder über die Knöpfe auswählen.",
                font=self._fonts["body"], text_color=muted, fg_color=bg)
            self._guide_footer.grid(row=4, column=0, columnspan=2, pady=(2, 0))
            return guide

        def _tree_heading_height(self) -> int:
            """Höhe der Tabellen-Kopfzeile (per identify_region ermittelt, DPI-unabhängig)."""
            height = 0
            for y in range(0, 150, 2):
                if self.tree.identify_region(20, y) == "heading":
                    height = y + 2
            return height or 40

        def _place_start_guide(self, _event=None) -> None:
            """Setzt die Anleitung mittig in den Bereich UNTER der Kopfzeile. Reicht die
            Höhe nicht, werden erst Fußzeile, dann Erläuterungen ausgeblendet – so ragt
            sie nie über die Tabelle hinaus."""
            guide = getattr(self, "_start_guide", None)
            if guide is None or not getattr(self, "_guide_on", False):
                return
            head = self._tree_heading_height()
            available = self.tree.winfo_height() - head - 12
            for w in (*self._guide_bodies, self._guide_footer):
                w.grid()
            wrap = max(260, min(560, self.tree.winfo_width() - 120))
            for w in self._guide_bodies:
                w.configure(wraplength=wrap)
            guide.update_idletasks()
            if guide.winfo_reqheight() > available:
                self._guide_footer.grid_remove()
                guide.update_idletasks()
            if guide.winfo_reqheight() > available:
                for w in self._guide_bodies:
                    w.grid_remove()
                guide.update_idletasks()
            y = head + max(6, (available - guide.winfo_reqheight()) // 2)
            guide.place(in_=self.tree, relx=0.5, y=y, anchor="n")

        def _update_empty_hint(self) -> None:
            """Zeigt über der leeren Tabelle einen Hinweis (Start bzw. keine Treffer)."""
            if not hasattr(self, "_empty_hint"):
                return
            self._empty_hint.place_forget()
            self._start_guide.place_forget()
            self._guide_on = False
            if self.visible_iids:
                return
            self._guide_on = not self.candidates
            if self._guide_on:
                self._place_start_guide()
            else:
                self._empty_hint.configure(
                    text="Keine Treffer für den aktuellen Filter bzw. die Suche.")
                self._empty_hint.place(relx=0.5, rely=0.4, anchor="center")

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
            if region == "cell" and row and self._is_ref_column(column):
                c = self.candidates[int(row)]
                if self._refs_for(c) is not None:
                    self._open_xref_popup(c)
                    return "break"
            return None

        def _is_ref_column(self, identify_result: str) -> bool:
            return any(self._is_column(identify_result, col) for col in self._REF_COLUMNS)

        @staticmethod
        def _as_link_text(text: str) -> str:
            """Kennzeichnet eine klickbare Verweise-Zahl mit ' ↗' (Link-Optik in der Zelle).

            Bewusst ein rendering-unabhängiges Symbol-Suffix statt eines Unicode-
            Unterstrichs (U+0332): letzterer wurde von der Treeview-Zeilenhöhe
            abgeschnitten. ttk.Treeview erlaubt keine zellgenaue Schrift/Farbe,
            daher signalisiert das Suffix – kombiniert mit dem hand2-Cursor – die
            Klickbarkeit.
            """
            return f"{text} ↗"

        def _is_xref_link_row(self, row: str) -> bool:
            """True, wenn die Verweise-Zelle dieser Zeile klickbar ist (Datenpunkt vorhanden)."""
            try:
                return self._refs_for(self.candidates[int(row)]) is not None
            except (ValueError, IndexError):
                return False

        def _on_tree_motion(self, event) -> None:
            """Zeigt hand2-Cursor über klickbaren Verweise-Zellen, sonst Standardcursor."""
            region = self.tree.identify("region", event.x, event.y)
            column = self.tree.identify_column(event.x)
            row    = self.tree.identify_row(event.y)
            over_link = (
                region == "cell" and bool(row)
                and self._is_ref_column(column)
                and self._is_xref_link_row(row)
            )
            cursor = "hand2" if over_link else ""
            if self.tree.cget("cursor") != cursor:
                self.tree.configure(cursor=cursor)

        def _is_column(self, identify_result: str, name: str) -> bool:
            """Prüft, ob eine identify_column()-Kennung (#N) der Datenspalte 'name' entspricht.

            identify_column zählt nur die SICHTBAREN Spalten (displaycolumns), die je
            nach Ansichtsmodus wechseln – daher gegen diese Liste prüfen.
            """
            try:
                idx = int(identify_result.replace("#", ""))
            except ValueError:
                return False
            shown = tuple(self.tree["displaycolumns"])
            if not shown or shown == ("#all",):
                shown = tuple(self.tree["columns"])
            return 1 <= idx <= len(shown) and shown[idx - 1] == name

        def _source_dir(self) -> Optional[str]:
            """Ordner der geladenen GPA- (sonst ETS-)Datei als Startordner für Speichern-Dialoge."""
            for var in (self.gpa_var, self.ets_var):
                text = var.get().strip()
                if text and Path(text).parent.is_dir():
                    return str(Path(text).parent)
            return None

        def on_tree_double_click(self, event) -> Optional[str]:
            region = self.tree.identify("region", event.x, event.y)
            column = self.tree.identify_column(event.x)
            row    = self.tree.identify_row(event.y)
            if region == "cell" and self._is_column(column, "new") and row:
                self.start_edit_new_name(row)
                return "break"
            # Sonst: Doppelklick auf eine Zeile zeigt ihre Verwendungen im GPA-Projekt
            # (nicht in den Verweise-Spalten – dort öffnet schon der Einfachklick).
            if region == "cell" and row and not self._is_ref_column(column):
                c = self.candidates[int(row)]
                if self._refs_for(c) is not None:
                    self._open_xref_popup(c)
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
            bbox = self.tree.bbox(row, "new")
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
                    self._center_dialog("Hinweis")
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
                ["Sync", "Status", "GA", "Raum", "Aktueller GPA-Name", "Neuer GPA-Name aus ETS",
                 "Visu", "Logik", "Zeitschaltuhr", "Datei im GPA"]]
            for iid in iids:
                try:
                    c = self.candidates[int(iid)]
                except (IndexError, ValueError):
                    continue
                counts = [str(n) if n >= 0 else ""
                          for n in (self._ref_count(c, col) for col in self._REF_COLUMNS)]
                refs = self._refs_for(c)
                rooms = " | ".join(refs.rooms) if refs is not None else ""
                rows.append(["ja" if c.selected else "nein",
                              c.status, c.group_address, rooms,
                              c.current_name, c.new_name, *counts, c.zip_path])
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
                self.detail_ga_roles.configure(text="")
                self.detail_ga_roles.grid_remove()
                self._show_detail_fields(False)
                self._schedule_detail_xrefs(None)
                return
            self._show_detail_fields(True)
            c = self.candidates[int(selected[0])]
            self.detail_vars["status"].set(c.status)
            self.detail_vars["ga"].set(c.group_address)
            dp = self.datapoint_by_path.get(c.zip_path) if c.zip_path else None
            roles = format_ga_roles(dp) if dp is not None else ""
            self.detail_ga_roles.configure(text=roles)
            self.detail_ga_roles.grid() if roles else self.detail_ga_roles.grid_remove()
            self.detail_vars["source"].set(source_label(c.source_field))
            self.detail_vars["old"].set(c.current_name)
            self.detail_vars["new"].set(c.new_name)
            self._schedule_detail_xrefs(c)

        def _schedule_detail_xrefs(self, candidate: Optional[SyncCandidate]) -> None:
            """Leichter Debounce (50 ms): beim schnellen Durchscrollen wird nur die
            zuletzt markierte Zeile aufgelöst, nicht jede Zwischenzeile."""
            if self._xref_debounce_id is not None:
                try:
                    self.after_cancel(self._xref_debounce_id)
                except Exception:  # pragma: no cover - defensiv
                    pass
            self._xref_debounce_id = self.after(
                50, lambda: self._populate_detail_xrefs(candidate))

        # ── GPA-Verweise: Darstellung (Panel + Popup) ──────────────────────────

        _ROLE_TEXT = {
            "Eingang": ("Eingang – Logik reagiert auf diesen Datenpunkt", "Eingang (Logik reagiert)"),
            "Ausgang": ("Ausgang – Logik sendet auf diesen Datenpunkt", "Ausgang (Logik sendet)"),
        }

        def _render_entry(self, parent, row: int, main: str, subs: Sequence[str], *,
                          wrap: int, compact: bool, warn: bool = False) -> None:
            """Ein Verweis-Eintrag: Punkt in eigener Spalte, daneben Hauptzeile und
            gedämpfte Nebenzeilen – so bleiben auch umbrochene Zeilen bündig eingerückt."""
            entry = ctk.CTkFrame(parent, fg_color="transparent")
            entry.grid(row=row, column=0, sticky="ew", padx=6, pady=(1, 6))
            entry.columnconfigure(1, weight=1)
            ctk.CTkLabel(entry, text="•", font=self._fonts["body"], width=14,
                         anchor="nw").grid(row=0, column=0, sticky="nw")
            ctk.CTkLabel(entry, text=main, font=self._fonts["body"],
                         justify="left", anchor="w", wraplength=max(120, wrap - 20),
                         text_color=("#b45309", "#fbbf24") if warn else None).grid(
                row=0, column=1, sticky="ew")
            for i, sub in enumerate(s for s in subs if s):
                ctk.CTkLabel(entry, text=sub, font=self._fonts["detail_sub"], justify="left",
                             text_color=("gray30", "gray70"), anchor="w", height=20,
                             wraplength=max(120, wrap - 20)).grid(
                    row=i + 1, column=1, sticky="ew")

        def _render_visu_entry(self, parent, row: int, ref: VisuReference, *,
                               wrap: int, compact: bool) -> None:
            if ref.orphan:
                self._render_entry(parent, row, "unbekannte Ansicht",
                                   ["Verweis zeigt auf eine nicht vorhandene Ansicht"],
                                   wrap=wrap, compact=compact, warn=True)
                return
            # Breadcrumb endet mit der Kachel; "(Raum)"-Suffix des letzten Standorts
            # entfällt, im Panel zusätzlich der immer gleiche Wurzelknoten.
            loc = re.sub(r"\s*\([^()]*\)\s*$", "", ref.location).strip() if ref.location else ""
            if compact:
                loc = re.sub(r"^Gebäude und Geräte\s*→\s*", "", loc)
            main = f"{loc} → {ref.view_name}" if loc else ref.view_name
            subs: List[str] = []
            if ref.channel_type:
                german = channel_type_display_name(ref.function_type, ref.channel_type)
                if german:
                    subs.append(german if compact else f"{german} ({ref.channel_type})")
                else:
                    subs.append(ref.channel_type)
            # Benutzer: im Popup immer, im Panel nur bei Abweichung vom projekttypischen
            # Normalfall (sonst stünde bei jeder Ansicht dieselbe Zeile).
            if ref.users and (not compact or ref.users != self._default_users):
                subs.append("👤 Sichtbar für: " + ", ".join(ref.users))
            self._render_entry(parent, row, main, subs, wrap=wrap, compact=compact)

        def _render_logic_entry(self, parent, row: int, ref: LogicReference, *,
                                wrap: int, compact: bool) -> None:
            long_text, short_text = self._ROLE_TEXT.get(ref.role, (ref.role, ref.role))
            subs = [short_text if compact else long_text]
            if ref.node_name and not compact:
                subs.append(f"Baustein-Beschriftung: {ref.node_name}")
            if not ref.page_active:
                subs.append("⚠ Logikseite ist deaktiviert")
            self._render_entry(parent, row, f"Logikseite „{ref.page_name}“", subs,
                               wrap=wrap, compact=compact)

        def _render_timer_entry(self, parent, row: int, ref: TimerReference, *,
                                wrap: int, compact: bool) -> None:
            if ref.schedules:
                limit = 3 if compact else 8
                times = ", ".join(ref.schedules[:limit])
                if len(ref.schedules) > limit:
                    times += f" … (+{len(ref.schedules) - limit})"
                subs = [f"Schaltzeiten: {times}",
                        f"{ref.active_count} von {len(ref.schedules)} aktiv"]
            else:
                subs = ["keine Schaltzeiten hinterlegt"]
            self._render_entry(parent, row, f"Ansicht „{ref.view_name}“", subs,
                               wrap=wrap, compact=compact)

        def _render_reference_sections(self, parent, refs: DatapointReferences, *,
                                       wrap: int, compact: bool,
                                       per_section_limit: Optional[int] = None) -> int:
            """Rendert die Abschnitte Visualisierung / Logik / Zeitschaltuhr.

            Gemeinsam genutzt von Eigenschaften-Panel (compact) und Popup, damit
            Optik und Format identisch bleiben. Rückgabe: nächste freie grid-Zeile.
            """
            row = 0
            sections = (
                ("🖥", "Visualisierung", refs.visu, self._render_visu_entry),
                ("⚙", "Logik", refs.logic, self._render_logic_entry),
                ("⏰", "Zeitschaltuhr", refs.timers, self._render_timer_entry),
            )
            for icon, title, items, render in sections:
                if not items:
                    continue
                ctk.CTkLabel(parent, text=f"{icon}  {title} ({len(items)})",
                             font=self._fonts["body_bold"],
                             text_color=(ACCENT_DARK, ACCENT), anchor="w").grid(
                    row=row, column=0, sticky="ew", padx=4, pady=(10 if row else 2, 2))
                row += 1
                shown = items if per_section_limit is None else items[:per_section_limit]
                for item in shown:
                    render(parent, row, item, wrap=wrap, compact=compact)
                    row += 1
                if len(items) > len(shown):
                    ctk.CTkLabel(parent,
                                 text=f"+{len(items) - len(shown)} weitere – vollständige "
                                      "Liste per Klick auf die Zahl in der Tabelle",
                                 font=self._fonts["small"], justify="left",
                                 text_color=("gray30", "gray70"), anchor="w",
                                 wraplength=wrap).grid(
                        row=row, column=0, sticky="ew", padx=10, pady=(0, 4))
                    row += 1
            return row

        @staticmethod
        def _references_as_text(candidate: SyncCandidate, refs: DatapointReferences) -> str:
            """Mehrzeiliger Klartext der Verwendungen (für die Zwischenablage)."""
            lines = [f"Datenpunkt: {candidate.current_name} ({candidate.group_address})"]
            if refs.is_unused:
                lines.append("Keine Verwendung in Visu, Logik oder Zeitschaltuhr.")
            for v in refs.visu:
                where = f"{v.location} → {v.view_name}" if v.location else v.view_name
                users = f" [sichtbar für: {', '.join(v.users)}]" if v.users else ""
                lines.append(f"Visu: {where}{users}")
            for lg in refs.logic:
                state = "" if lg.page_active else " [Seite deaktiviert]"
                lines.append(f"Logik: {lg.page_name} – {lg.role}"
                             f"{' – ' + lg.node_name if lg.node_name else ''}{state}")
            for t in refs.timers:
                times = ", ".join(t.schedules) if t.schedules else "keine Schaltzeiten"
                lines.append(f"Zeitschaltuhr: {t.view_name} – {times}")
            return "\n".join(lines)

        def _populate_detail_xrefs(self, candidate: Optional[SyncCandidate]) -> None:
            """Baut die Verweise im Eigenschaften-Panel bei jedem Zeilenwechsel neu auf.

            - kein GPA-Datenpunkt: "-"
            - keine Verwendung: Hinweis "nirgends verwendet"
            - sonst: gegliederte Liste (Visualisierung / Logik / Zeitschaltuhr).
            """
            if not hasattr(self, "detail_xref_frame"):
                return
            for child in self.detail_xref_frame.winfo_children():
                child.destroy()
            try:
                self.detail_xref_frame._parent_canvas.yview_moveto(0)
            except Exception:  # pragma: no cover - interne CTk-API, rein kosmetisch
                pass

            def _muted(text: str) -> None:
                ctk.CTkLabel(self.detail_xref_frame, text=text,
                             font=self._fonts["body"], justify="left",
                             text_color=("gray30", "gray70"),
                             anchor="w", wraplength=235).grid(
                    row=0, column=0, sticky="ew", padx=6, pady=(2, 4))

            # Scrollbalken erst nach dem Aufbau prüfen (nur zeigen, wenn nötig). Zweimal
            # zeitversetzt, weil sich die Panelhöhe beim Ein-/Ausblenden der Felder
            # erst nach dem nächsten Layout-Durchlauf einstellt.
            self.after(40, self._update_xref_scrollbar)
            self.after(250, self._update_xref_scrollbar)
            refs = self._refs_for(candidate) if candidate is not None else None
            if candidate is None:
                self.detail_xref_header.configure(text="GPA-Verweise")
                _muted("Zeile in der Tabelle auswählen, um Adressen und "
                       "Verwendungen des Datenpunkts zu sehen.")
                return
            if refs is None:
                self.detail_xref_header.configure(text="GPA-Verweise")
                _muted("Kein GPA-Datenpunkt (nur in der ETS vorhanden).")
                return
            self.detail_xref_header.configure(text=f"GPA-Verweise ({refs.total})")
            if refs.is_unused:
                _muted("Nirgends verwendet – weder in einer Visu-Ansicht, "
                       "in der Logik noch in einer Zeitschaltuhr.")
                return
            self._render_reference_sections(self.detail_xref_frame, refs,
                                            wrap=235, compact=True, per_section_limit=10)

        def _update_xref_scrollbar(self) -> None:
            """Blendet den Scrollbalken des Verweise-Bereichs nur ein, wenn der Inhalt
            nicht in die sichtbare Höhe passt (CTkScrollableFrame zeigt ihn sonst immer)."""
            frame = getattr(self, "detail_xref_frame", None)
            if frame is None:
                return
            try:
                frame.update_idletasks()
                # Tatsächliche Unterkante des Inhalts (winfo_reqheight des Rahmens
                # enthält eine CTk-Mindesthöhe und ist daher unbrauchbar).
                needed = max((w.winfo_y() + w.winfo_height() for w in frame.winfo_children()),
                             default=0)
                available = frame._parent_canvas.winfo_height()
                if needed <= available:
                    frame._scrollbar.grid_remove()
                    frame._parent_canvas.yview_moveto(0)
                else:
                    frame._scrollbar.grid()
            except Exception:  # pragma: no cover - interne CTk-API, rein kosmetisch
                pass

        # ── Querverweise-Popup ─────────────────────────────────────────────────

        def _open_xref_popup(self, candidate: SyncCandidate) -> None:
            """Zeigt alle Verwendungen des Datenpunkts (Visu, Logik, Zeitschaltuhr)."""
            refs = self._refs_for(candidate) or DatapointReferences()

            dialog = ctk.CTkToplevel(self)
            dialog.title("Verwendungen im GPA-Projekt")
            dialog.geometry("600x560")
            dialog.minsize(420, 320)
            dialog.transient(self)
            dialog.columnconfigure(0, weight=1)
            dialog.rowconfigure(3, weight=1)

            ctk.CTkLabel(dialog, text="🔗  Verwendungen im GPA-Projekt",
                         font=self._fonts["normal"]).grid(
                row=0, column=0, padx=20, pady=(18, 4), sticky="w")
            ga = f"  ·  GA {candidate.group_address}" if candidate.group_address else ""
            ctk.CTkLabel(dialog, text=f"Datenpunkt: {candidate.current_name}{ga}",
                         font=self._fonts["body"], justify="left",
                         text_color=("gray30", "gray70"), wraplength=550).grid(
                row=1, column=0, padx=20, pady=(0, 2), sticky="w")
            # Nur Kategorien nennen, die es im Projekt überhaupt gibt.
            counts = [f"{len(refs.visu)} Visu"]
            if self._project_has("logic"):
                counts.append(f"{len(refs.logic)} Logik")
            if self._project_has("timer"):
                counts.append(f"{len(refs.timers)} Zeitschaltuhr")
            ctk.CTkLabel(dialog,
                         text="  ·  ".join(counts),
                         font=self._fonts["body_bold"], anchor="w").grid(
                row=2, column=0, padx=20, pady=(0, 8), sticky="w")

            body = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
            body.grid(row=3, column=0, padx=14, pady=(0, 8), sticky="nsew")
            body.columnconfigure(0, weight=1)

            if refs.is_unused:
                ctk.CTkLabel(body,
                             text="Keine Verwendung gefunden.\n\n"
                                  "Der Datenpunkt wird weder in einer Visu-Ansicht noch in der "
                                  "Logik oder von einer Zeitschaltuhr verwendet und ist "
                                  "vermutlich aufräumbar. Vor dem Löschen bitte im GPA prüfen.",
                             font=self._fonts["body"], justify="left",
                             wraplength=520).grid(row=0, column=0, sticky="w", padx=6, pady=6)
            else:
                self._render_reference_sections(body, refs, wrap=520, compact=False)

            buttons = ctk.CTkFrame(dialog, fg_color="transparent")
            buttons.grid(row=4, column=0, padx=20, pady=(0, 18), sticky="ew")
            buttons.columnconfigure(0, weight=1)

            def _copy() -> None:
                self.clipboard_clear()
                self.clipboard_append(self._references_as_text(candidate, refs))
                self.status_var.set(f"Verwendungen von „{candidate.current_name}“ kopiert.")

            ctk.CTkButton(buttons, text="In Zwischenablage kopieren", width=200,
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=_copy).grid(row=0, column=0, sticky="w")
            ok_btn = ctk.CTkButton(buttons, text="Schließen", fg_color=ACCENT,
                                   hover_color=ACCENT_DARK, text_color="white",
                                   command=dialog.destroy)
            ok_btn.grid(row=0, column=1, sticky="e")

            dialog.bind("<Return>", lambda _e: dialog.destroy())
            dialog.bind("<Escape>", lambda _e: dialog.destroy())

            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            dialog.after(100, dialog.grab_set)
            dialog.after(120, ok_btn.focus_set)

        # ── Sync-Auswirkung ────────────────────────────────────────────────────

        def _confirm_sync_impact(self, selected: Sequence[SyncCandidate]) -> bool:
            """Zeigt vor dem Speichern, wo die Umbenennungen im GPA-Projekt wirken.

            Rückgabe True = weiter, False = abgebrochen.
            """
            impact = summarize_sync_impact(selected, self.references)
            result = {"ok": False}

            dialog = ctk.CTkToplevel(self)
            dialog.title("Synchronisation prüfen")
            dialog.geometry("640x600")
            dialog.minsize(480, 380)
            dialog.transient(self)
            dialog.columnconfigure(0, weight=1)
            dialog.rowconfigure(4, weight=1)

            ctk.CTkLabel(dialog, text="Auswirkung der Umbenennung",
                         font=self._fonts["normal"]).grid(
                row=0, column=0, padx=22, pady=(18, 4), sticky="w")
            renamed_text = ("1 Datenpunkt wird umbenannt." if impact.renamed == 1
                            else f"{impact.renamed} Datenpunkte werden umbenannt.")
            ctk.CTkLabel(dialog, text=renamed_text,
                         font=self._fonts["body_bold"], anchor="w").grid(
                row=1, column=0, padx=22, pady=(0, 6), sticky="w")

            stats = ctk.CTkFrame(dialog, corner_radius=8, border_width=1,
                                 border_color=("gray78", "gray28"))
            stats.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="ew")
            stats.columnconfigure((0, 1), weight=1, uniform="stat")
            def _n(count: int, one: str, many: str) -> str:
                return f"{count} {one if count == 1 else many}"

            stat_defs = [
                ("🖥", f"{impact.in_visu} in Visu-Ansichten",
                 _n(len(impact.views), "Ansicht betroffen", "Ansichten betroffen")),
                ("⚙", f"{impact.in_logic} in der Logik",
                 _n(len(impact.logic_pages), "Logikseite betroffen", "Logikseiten betroffen")),
                ("⏰", f"{impact.in_timers} mit Zeitschaltuhr", ""),
                ("○", f"{impact.unused} nirgends verwendet", ""),
            ]
            for i, (icon, main, sub) in enumerate(stat_defs):
                cell = ctk.CTkFrame(stats, fg_color="transparent")
                cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=12, pady=6)
                ctk.CTkLabel(cell, text=f"{icon}  {main}", font=self._fonts["body"],
                             anchor="w").grid(row=0, column=0, sticky="w")
                if sub:
                    ctk.CTkLabel(cell, text=sub, font=self._fonts["detail_sub"],
                                 text_color=("gray30", "gray70"), anchor="w").grid(
                        row=1, column=0, sticky="w", padx=(26, 0))

            ctk.CTkLabel(dialog,
                         text="Umbenannt wird nur der Datenpunktname. Ansichten, Logikseiten "
                              "und Baustein-Beschriftungen behalten ihre eigenen Namen.",
                         font=self._fonts["detail_sub"], justify="left", wraplength=590,
                         text_color=("gray30", "gray70")).grid(
                row=3, column=0, padx=22, pady=(0, 6), sticky="w")

            body = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
            body.grid(row=4, column=0, padx=14, pady=(0, 8), sticky="nsew")
            body.columnconfigure(0, weight=1)
            limit = 300
            for i, (c, refs) in enumerate(impact.rows[:limit]):
                if refs is None:
                    where = ""
                elif refs.is_unused:
                    where = "nicht verwendet"
                else:
                    parts = []
                    if refs.visu:
                        parts.append(f"Visu: {', '.join(v.view_name for v in refs.visu[:3])}"
                                     + (" …" if len(refs.visu) > 3 else ""))
                    if refs.logic:
                        pages = list(dict.fromkeys(lg.page_name for lg in refs.logic))
                        parts.append(f"Logik: {', '.join(pages[:3])}"
                                     + (" …" if len(pages) > 3 else ""))
                    if refs.timers:
                        parts.append(f"Zeitschaltuhr: {len(refs.timers)}")
                    where = "  ·  ".join(parts)
                self._render_entry(body, i, f"{c.current_name}  →  {c.new_name}",
                                   [where], wrap=560, compact=False)
            if len(impact.rows) > limit:
                ctk.CTkLabel(body, text=f"+{len(impact.rows) - limit} weitere",
                             font=self._fonts["small"], anchor="w").grid(
                    row=limit, column=0, sticky="w", padx=10)

            buttons = ctk.CTkFrame(dialog, fg_color="transparent")
            buttons.grid(row=5, column=0, padx=20, pady=(0, 18), sticky="ew")
            buttons.columnconfigure(0, weight=1)

            def _ok() -> None:
                result["ok"] = True
                dialog.destroy()

            ctk.CTkButton(buttons, text="Abbrechen", width=120,
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=dialog.destroy).grid(row=0, column=1, sticky="e", padx=(0, 8))
            ok_btn = ctk.CTkButton(buttons, text="Weiter zum Speichern", width=180,
                                   fg_color=ACCENT, hover_color=ACCENT_DARK,
                                   text_color="white", command=_ok)
            ok_btn.grid(row=0, column=2, sticky="e")

            dialog.bind("<Return>", lambda _e: _ok())
            dialog.bind("<Escape>", lambda _e: dialog.destroy())
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            dialog.after(100, dialog.grab_set)
            dialog.after(120, ok_btn.focus_set)
            self.wait_window(dialog)
            return result["ok"]

        # ── CSV-Export ─────────────────────────────────────────────────────────

        def save_csv(self) -> None:
            if not self.candidates:
                self._center_dialog("Hinweis")
                messagebox.showinfo("Hinweis", "Bitte zuerst auf 'Analysieren' klicken.")
                return
            path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialdir=self._source_dir(),
                initialfile="gpa_sync_pruefliste.csv")
            if not path:
                return
            try:
                export_candidates_csv(self.candidates, Path(path),
                                      references=self.references or None)
                self.status_var.set(f"CSV gespeichert: {path}")
            except Exception as e:
                self._center_dialog("Fehler beim CSV-Export")
                messagebox.showerror("Fehler beim CSV-Export", str(e))

        # ── Synchronisierung ───────────────────────────────────────────────────

        def _validate_selected_names(self) -> bool:
            selected_updates = {
                c.zip_path: c.new_name.strip()
                for c in self.candidates
                if c.selected and c.status == SyncStatus.AENDERUNG
            }
            if not selected_updates:
                self._center_dialog("Hinweis")
                messagebox.showinfo("Hinweis",
                    "Keine Änderungen ausgewählt. Bitte mindestens eine Zeile auswählen.")
                return False
            if any(not n for n in selected_updates.values()):
                self._center_dialog("Ungültiger Name")
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
                self._center_dialog("Doppelte Namen")
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
            if not self._confirm_sync_impact(selected):
                self.status_var.set("Synchronisierung abgebrochen.")
                return
            input_gpa = Path(self.gpa_var.get())
            out = filedialog.asksaveasfilename(
                defaultextension=".gpa",
                filetypes=[("GPA-Projekt", "*.gpa")],
                # Speichern startet im Ordner des importierten GPA-Projekts.
                initialdir=str(input_gpa.parent),
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
            self._show_sync_done_dialog(changed, out, check_text)

        def _show_sync_done_dialog(self, changed: int, out: str, check_text: str) -> None:
            """Erfolgs-Dialog mit Erfolgsmeldung und dezentem Ko-fi-Spendenhinweis.

            Ersetzt das frühere messagebox.showinfo, damit ein Ko-fi-Button
            eingebettet werden kann und der Dialog dem Dark/Light-Theme folgt.
            """
            WRAP = 432  # Zeilenumbruch-Breite (Dialog ~480px abzüglich Innenabstand)

            dialog = ctk.CTkToplevel(self)
            dialog.title("Fertig")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.columnconfigure(0, weight=1)

            # ── Erfolgsmeldung ────────────────────────────────────────────────
            ctk.CTkLabel(dialog, text="✅  Fertig",
                         font=self._fonts["normal"]).grid(
                row=0, column=0, padx=24, pady=(20, 8), sticky="w")

            ctk.CTkLabel(dialog, text=f"{changed} Datenpunkte geändert.",
                         font=self._fonts["body_bold"], justify="left",
                         wraplength=WRAP).grid(
                row=1, column=0, padx=24, pady=(0, 8), sticky="w")

            ctk.CTkLabel(dialog, text=f"Neue GPA-Datei:\n{out}",
                         font=self._fonts["body"], justify="left",
                         wraplength=WRAP).grid(
                row=2, column=0, padx=24, pady=(0, 8), sticky="w")

            check_msg = check_text.strip()
            if check_msg:
                ctk.CTkLabel(dialog, text=check_msg,
                             font=self._fonts["body"], justify="left",
                             wraplength=WRAP).grid(
                    row=3, column=0, padx=24, pady=(0, 8), sticky="w")

            ctk.CTkLabel(dialog, text="Bitte zuerst als Kopie im GPA öffnen und prüfen.",
                         font=self._fonts["body"], justify="left",
                         wraplength=WRAP).grid(
                row=4, column=0, padx=24, pady=(0, 14), sticky="w")

            # ── Trennlinie ────────────────────────────────────────────────────
            tk.Frame(dialog, height=1, bg=self._p["border"]).grid(
                row=5, column=0, sticky="ew", padx=24, pady=(0, 12))

            # ── Dezenter Spendenhinweis ───────────────────────────────────────
            ctk.CTkLabel(dialog,
                         text="☕  Wenn dir das Tool geholfen hat,\n"
                              "freue ich mich über deine Unterstützung!",
                         font=self._fonts["body"], justify="left",
                         text_color=("gray35", "gray65"),
                         wraplength=WRAP).grid(
                row=6, column=0, padx=24, pady=(0, 4), sticky="w")

            ctk.CTkButton(dialog, text="☕ Ko-fi", width=110,
                          fg_color="transparent", border_width=1,
                          border_color=("gray60", "gray45"),
                          text_color=("gray15", "gray85"),
                          hover_color=("gray85", "gray25"),
                          command=lambda: webbrowser.open(_KOFI_URL)).grid(
                row=7, column=0, padx=24, pady=(0, 14), sticky="e")

            # ── Hauptbutton (OK) ──────────────────────────────────────────────
            ok_btn = ctk.CTkButton(dialog, text="OK", fg_color=ACCENT,
                                   hover_color=ACCENT_DARK, text_color="white",
                                   command=dialog.destroy)
            ok_btn.grid(row=8, column=0, padx=24, pady=(0, 20), sticky="e")

            dialog.bind("<Return>", lambda _e: dialog.destroy())
            dialog.bind("<Escape>", lambda _e: dialog.destroy())

            # Mittig im Tool-Fenster positionieren.
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")

            # grab_set erst nach dem ersten Rendern, sonst flackert das Fenster.
            dialog.after(100, dialog.grab_set)
            dialog.after(120, ok_btn.focus_set)

        def _sync_error(self, error: Exception) -> None:
            _log.error("Synchronisierungsfehler: %s", error, exc_info=True)
            self._set_busy(False)
            self.status_var.set("Synchronisierung fehlgeschlagen.")
            self._center_dialog("Fehler beim Synchronisieren")
            messagebox.showerror("Fehler beim Synchronisieren", str(error))

    App().mainloop()
