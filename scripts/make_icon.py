"""Generate the Wallcraft icon (PNG + multi-size ICO) into src/wallcraft/resources.

Usage:  python scripts/make_icon.py        (requires PySide6 and Pillow)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
)

OUT = Path(__file__).resolve().parents[1] / "src" / "wallcraft" / "resources"


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    s = float(size)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    margin = s * 0.04
    rect = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
    tile = QPainterPath()
    tile.addRoundedRect(rect, s * 0.22, s * 0.22)
    sky = QLinearGradient(0, rect.top(), 0, rect.bottom())
    sky.setColorAt(0.0, QColor("#262A6E"))
    sky.setColorAt(0.5, QColor("#6B5BD2"))
    sky.setColorAt(0.85, QColor("#F2995E"))
    p.fillPath(tile, sky)
    p.setClipPath(tile)

    sun_c = QPointF(s * 0.5, s * 0.60)
    glow = QRadialGradient(sun_c, s * 0.34)
    glow.setColorAt(0.0, QColor(255, 220, 160, 150))
    glow.setColorAt(1.0, QColor(255, 220, 160, 0))
    p.fillRect(rect, glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFE6A8"))
    p.drawEllipse(sun_c, s * 0.17, s * 0.17)

    back = QPainterPath()
    back.moveTo(rect.left(), s * 0.72)
    back.cubicTo(s * 0.30, s * 0.60, s * 0.45, s * 0.70, s * 0.62, s * 0.66)
    back.cubicTo(s * 0.78, s * 0.62, s * 0.88, s * 0.64, rect.right(), s * 0.60)
    back.lineTo(rect.right(), rect.bottom())
    back.lineTo(rect.left(), rect.bottom())
    back.closeSubpath()
    p.fillPath(back, QColor("#3A2F7A"))

    front = QPainterPath()
    front.moveTo(rect.left(), s * 0.80)
    front.cubicTo(s * 0.25, s * 0.72, s * 0.50, s * 0.86, s * 0.72, s * 0.78)
    front.cubicTo(s * 0.85, s * 0.74, s * 0.92, s * 0.76, rect.right(), s * 0.74)
    front.lineTo(rect.right(), rect.bottom())
    front.lineTo(rect.left(), rect.bottom())
    front.closeSubpath()
    p.fillPath(front, QColor("#1B1A45"))
    p.end()
    return img


def main() -> int:
    _app = QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    big = draw(512)
    draw(256).save(str(OUT / "icon.png"), "PNG")
    big.save(str(OUT / "icon-512.png"), "PNG")
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; writing single-size ICO with Qt")
        draw(256).save(str(OUT / "icon.ico"), "ICO")
        return 0
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = []
    for n in sizes:
        q = draw(n).convertToFormat(QImage.Format.Format_RGBA8888)
        frames.append(Image.frombuffer("RGBA", (n, n), bytes(q.constBits()), "raw", "RGBA", 0, 1))
    frames[-1].save(OUT / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes], append_images=frames[:-1])
    print(f"Wrote icons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
