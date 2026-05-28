"""
Erzeugt das App-Icon fuer ETS GPA Sync.
Konzept: Datenfluss zwischen zwei Datenpunkt-Sammlungen
  Links:  Kreis (Outline) mit 3 gruenen Punkten = GPA-Datenpunkte
  Mitte:  Pfeil (3 Dots + Spitze) = Synchronisation
  Rechts: Kreis (gefuellt) mit 3 dunklen Punkten = synchronisiert

Aufruf: py create_icon.py
Ausgabe: gpa_ga_sync/assets/app_icon.ico + app_icon.png
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

BG_COLOR    = "#1a1a1a"
GREEN       = "#10b981"
DARK        = "#1a1a1a"

ASSETS_DIR  = Path(__file__).parent / "gpa_ga_sync" / "assets"
ICO_SIZES   = [256, 128, 64, 48, 32, 16]


def draw_icon(size: int) -> Image.Image:
    """Zeichnet das Icon in der gewuenschten Zielgroesse (RGBA)."""
    # 4-fache Aufloesung fuer sauberes Anti-Aliasing, dann runterskalieren
    s = size * 4

    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    # ── Hintergrund mit abgerundeten Ecken ─────────────────────────────────
    rx = round(s * 0.18)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=rx, fill=BG_COLOR)

    # ── Geometrie-Parameter ─────────────────────────────────────────────────
    cx_l = round(s * 0.22)   # Zentrum linker Kreis (x)
    cx_r = round(s * 0.82)   # Zentrum rechter Kreis (x)
    cy   = s // 2             # Vertikal zentriert
    cr   = round(s * 0.17)   # Kreisradius

    stroke = max(2, round(s * 0.028))   # Outline-Staerke linker Kreis
    dr     = max(1, round(s * 0.025))   # Radius der kleinen Punkte

    dot_ys = [round(s * f) for f in (0.42, 0.50, 0.58)]  # y-Positionen Punkte

    # ── Linker Kreis: Outline ───────────────────────────────────────────────
    d.ellipse(
        [cx_l - cr, cy - cr, cx_l + cr, cy + cr],
        outline=GREEN, width=stroke,
    )
    # Punkte darin: gruen
    for dy in dot_ys:
        d.ellipse([cx_l - dr, dy - dr, cx_l + dr, dy + dr], fill=GREEN)

    # ── Rechter Kreis: gefuellt ─────────────────────────────────────────────
    d.ellipse(
        [cx_r - cr, cy - cr, cx_r + cr, cy + cr],
        fill=GREEN,
    )
    # Punkte darin: dunkel (Hintergrundfarbe)
    for dy in dot_ys:
        d.ellipse([cx_r - dr, dy - dr, cx_r + dr, dy + dr], fill=DARK)

    # ── Pfeil: 3 Dots horizontal ────────────────────────────────────────────
    for fx in (0.40, 0.47, 0.54):
        dx = round(s * fx)
        d.ellipse([dx - dr, cy - dr, dx + dr, cy + dr], fill=GREEN)

    # ── Pfeilspitze (V-Form, keine Fuellung) ───────────────────────────────
    ax1 = round(s * 0.58)
    ay1 = round(s * 0.44)
    ax2 = round(s * 0.625)
    ay2 = cy
    ax3 = round(s * 0.58)
    ay3 = round(s * 0.56)
    lw  = max(2, round(s * 0.025))
    d.line([(ax1, ay1), (ax2, ay2), (ax3, ay3)], fill=GREEN, width=lw)

    # ── Runterskalieren auf Zielgroesse ────────────────────────────────────
    return img.resize((size, size), Image.LANCZOS)


def draw_icon_transparent(size: int) -> Image.Image:
    """Wie draw_icon, aber ohne Hintergrund (transparent) fuer die Toolbar."""
    s = size * 4

    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    cx_l = round(s * 0.22)
    cx_r = round(s * 0.82)
    cy   = s // 2
    cr   = round(s * 0.17)

    stroke = max(2, round(s * 0.028))
    dr     = max(1, round(s * 0.025))
    dot_ys = [round(s * f) for f in (0.42, 0.50, 0.58)]

    # Linker Kreis: Outline
    d.ellipse([cx_l - cr, cy - cr, cx_l + cr, cy + cr],
              outline=GREEN, width=stroke)
    for dy in dot_ys:
        d.ellipse([cx_l - dr, dy - dr, cx_l + dr, dy + dr], fill=GREEN)

    # Rechter Kreis: gefuellt
    d.ellipse([cx_r - cr, cy - cr, cx_r + cr, cy + cr], fill=GREEN)
    for dy in dot_ys:
        d.ellipse([cx_r - dr, dy - dr, cx_r + dr, dy + dr], fill=(0, 0, 0, 0))

    # Pfeil: 3 Dots
    for fx in (0.40, 0.47, 0.54):
        dx = round(s * fx)
        d.ellipse([dx - dr, cy - dr, dx + dr, cy + dr], fill=GREEN)

    # Pfeilspitze
    ax1 = round(s * 0.58);  ay1 = round(s * 0.44)
    ax2 = round(s * 0.625); ay2 = cy
    ax3 = round(s * 0.58);  ay3 = round(s * 0.56)
    lw  = max(2, round(s * 0.025))
    d.line([(ax1, ay1), (ax2, ay2), (ax3, ay3)], fill=GREEN, width=lw)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    images = [draw_icon(sz) for sz in ICO_SIZES]

    # .ico mit allen Standardgroessen
    ico_path = ASSETS_DIR / "app_icon.ico"
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(sz, sz) for sz in ICO_SIZES],
        append_images=images[1:],
    )
    print(f"Gespeichert: {ico_path}")

    # .png (256x256) fuer Fallback / Referenz
    png_path = ASSETS_DIR / "app_icon.png"
    images[0].save(png_path, format="PNG")
    print(f"Gespeichert: {png_path}")

    # .png transparent (64x64) fuer Toolbar-CTkImage
    toolbar_path = ASSETS_DIR / "app_icon_toolbar.png"
    draw_icon_transparent(64).save(toolbar_path, format="PNG")
    print(f"Gespeichert: {toolbar_path}")

    print(f"ICO enthaelt: {', '.join(str(s) for s in ICO_SIZES)} px")


if __name__ == "__main__":
    main()
