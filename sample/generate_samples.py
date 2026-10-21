#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""샘플 이미지 15장 생성 — 과일 5 + 탈것 5 + 강아지 5 를 unsorted/ 에 섞어 둔다 (분류 연습용, 저작권 없음).

    python3 generate_samples.py   →  sample/unsorted/*.png + 빈 sample/fruit/ · vehicle/ · dog/
"""
import math
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QRadialGradient

W, H = 800, 600
HERE = Path(__file__).resolve().parent


def canvas(bg):
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor(bg))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    # 바닥 그림자
    p.setBrush(QColor(0, 0, 0, 40))
    p.drawEllipse(QRectF(W / 2 - 200, H - 140, 400, 50))
    return img, p


def ball(p, cx, cy, r, base, hi="#ffffff"):
    g = QRadialGradient(QPointF(cx - r * 0.35, cy - r * 0.35), r * 1.3)
    g.setColorAt(0, QColor(hi))
    g.setColorAt(0.25, QColor(base))
    g.setColorAt(1, QColor(base).darker(160))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)


def leaf(p, x, y, w, h, angle, color="#3c9a3c"):
    p.save(); p.translate(x, y); p.rotate(angle)
    p.setBrush(QColor(color)); p.drawEllipse(QRectF(0, -h / 2, w, h)); p.restore()


def apple(p):
    ball(p, 400, 320, 170, "#d42a2a", "#ff9a9a")
    p.setBrush(QColor("#5a3a1a")); p.drawRoundedRect(QRectF(392, 120, 16, 70), 6, 6)
    leaf(p, 405, 150, 110, 45, -25)


def banana(p):
    path = QPainterPath(QPointF(170, 260))
    path.cubicTo(250, 520, 560, 520, 650, 220)
    path.cubicTo(560, 420, 280, 420, 170, 260)
    p.setBrush(QColor("#f5d33a")); p.drawPath(path)
    p.setBrush(QColor("#5a4a1a")); p.drawEllipse(QPointF(170, 258), 14, 14); p.drawEllipse(QPointF(650, 222), 12, 12)


def grape(p):
    rows = [(5, 150), (4, 235), (3, 315), (2, 390), (1, 460)]
    for n, y in rows:
        for i in range(n):
            ball(p, 400 + (i - (n - 1) / 2) * 82, y, 46, "#6b2fa0", "#c9a0f0")
    p.setBrush(QColor("#5a3a1a")); p.drawRoundedRect(QRectF(392, 70, 14, 50), 5, 5)
    leaf(p, 405, 90, 120, 50, -10)


def orange(p):
    ball(p, 400, 320, 175, "#f08a1c", "#ffd29a")
    p.setBrush(QColor(0, 0, 0, 25))
    for i in range(60):
        a = i * 2.4; r = 30 + (i * 37) % 130
        p.drawEllipse(QPointF(400 + r * math.cos(a), 320 + r * math.sin(a)), 3, 3)
    leaf(p, 400, 150, 100, 40, -20)


def watermelon(p):
    p.setBrush(QColor("#2f7d32")); p.drawPie(QRectF(150, 100, 500, 500), 180 * 16, 180 * 16)
    p.setBrush(QColor("#e9f5d0")); p.drawPie(QRectF(175, 125, 450, 450), 180 * 16, 180 * 16)
    p.setBrush(QColor("#e8384f")); p.drawPie(QRectF(195, 145, 410, 410), 180 * 16, 180 * 16)
    p.setBrush(QColor("#222"))
    for x, y in [(300, 400), (360, 450), (440, 450), (500, 400), (400, 390), (330, 360), (470, 360)]:
        p.drawEllipse(QPointF(x, y), 8, 12)


def wheel(p, x, y, r):
    p.setBrush(QColor("#263238")); p.drawEllipse(QPointF(x, y), r, r)
    p.setBrush(QColor("#b0bec5")); p.drawEllipse(QPointF(x, y), r * 0.45, r * 0.45)


def car(p):
    p.setBrush(QColor("#e53935"))
    p.drawRoundedRect(QRectF(160, 290, 480, 120), 40, 40)
    body = QPainterPath(QPointF(270, 300)); body.lineTo(330, 200); body.lineTo(500, 200); body.lineTo(570, 300)
    body.closeSubpath(); p.drawPath(body)
    p.setBrush(QColor("#bbdefb"))
    win = QPainterPath(QPointF(300, 295)); win.lineTo(345, 220); win.lineTo(405, 220); win.lineTo(405, 295); win.closeSubpath()
    p.drawPath(win)
    win2 = QPainterPath(QPointF(425, 295)); win2.lineTo(425, 220); win2.lineTo(490, 220); win2.lineTo(540, 295); win2.closeSubpath()
    p.drawPath(win2)
    p.setBrush(QColor("#fff59d")); p.drawEllipse(QRectF(610, 320, 26, 22))
    wheel(p, 270, 415, 50); wheel(p, 530, 415, 50)


def bus(p):
    p.setBrush(QColor("#fbc02d")); p.drawRoundedRect(QRectF(130, 170, 540, 250), 30, 30)
    p.setBrush(QColor("#bbdefb"))
    for i in range(4):
        p.drawRoundedRect(QRectF(160 + i * 112, 200, 92, 80), 10, 10)
    p.drawRoundedRect(QRectF(608, 200, 46, 120), 8, 8)
    p.setBrush(QColor("#455a64")); p.drawRect(QRectF(130, 330, 540, 18))
    wheel(p, 240, 425, 48); wheel(p, 560, 425, 48)


def bicycle(p):
    p.setPen(QPen(QColor("#263238"), 14)); p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(240, 380), 100, 100); p.drawEllipse(QPointF(560, 380), 100, 100)
    p.setPen(QPen(QColor("#1e88e5"), 14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    frame = QPainterPath(QPointF(240, 380)); frame.lineTo(360, 250); frame.lineTo(520, 250); frame.lineTo(560, 380)
    frame.moveTo(240, 380); frame.lineTo(420, 380); frame.lineTo(360, 250); frame.moveTo(420, 380); frame.lineTo(520, 250)
    p.drawPath(frame)
    p.setPen(QPen(QColor("#263238"), 14, Qt.SolidLine, Qt.RoundCap)); p.drawLine(QPointF(520, 250), QPointF(505, 200))
    p.drawLine(QPointF(480, 200), QPointF(540, 195)); p.drawLine(QPointF(360, 250), QPointF(350, 215))
    p.setPen(Qt.NoPen); p.setBrush(QColor("#263238")); p.drawRoundedRect(QRectF(315, 200, 75, 22), 10, 10)


def airplane(p):
    p.setBrush(QColor("#90a4ae"))
    wing = QPainterPath(QPointF(370, 300)); wing.lineTo(250, 470); wing.lineTo(330, 470); wing.lineTo(470, 300); wing.closeSubpath()
    p.drawPath(wing)
    tail = QPainterPath(QPointF(170, 290)); tail.lineTo(120, 180); tail.lineTo(175, 180); tail.lineTo(240, 285); tail.closeSubpath()
    p.drawPath(tail)
    p.setBrush(QColor("#eceff1")); p.drawRoundedRect(QRectF(140, 260, 540, 80), 40, 40)
    p.setBrush(QColor("#1e88e5"))
    for i in range(8):
        p.drawEllipse(QPointF(260 + i * 45, 290), 10, 10)
    p.setBrush(QColor("#90a4ae"))
    wing2 = QPainterPath(QPointF(390, 300)); wing2.lineTo(300, 160); wing2.lineTo(360, 160); wing2.lineTo(470, 300); wing2.closeSubpath()
    p.drawPath(wing2)


def boat(p):
    p.setBrush(QColor("#1565c0"))
    hull = QPainterPath(QPointF(150, 360)); hull.lineTo(650, 360); hull.lineTo(570, 450); hull.lineTo(230, 450); hull.closeSubpath()
    p.drawPath(hull)
    p.setBrush(QColor("#6d4c41")); p.drawRect(QRectF(392, 120, 14, 240))
    p.setBrush(QColor("#ffffff"))
    sail = QPainterPath(QPointF(410, 130)); sail.lineTo(410, 340); sail.lineTo(590, 340); sail.closeSubpath(); p.drawPath(sail)
    sail2 = QPainterPath(QPointF(388, 160)); sail2.lineTo(388, 340); sail2.lineTo(250, 340); sail2.closeSubpath(); p.drawPath(sail2)
    p.setBrush(QColor("#e53935")); p.drawRect(QRectF(406, 110, 50, 26))
    p.setPen(QPen(QColor("#4fc3f7"), 8)); p.setBrush(Qt.NoBrush)
    for x in range(140, 680, 80): p.drawArc(QRectF(x, 455, 80, 40), 0, 180 * 16)
    p.setPen(Qt.NoPen)


def dog(p, fur, ear, ear_style, spot=None, tongue=False):
    """정면 강아지 얼굴 — 털색·귀 모양으로 품종 느낌만 낸다."""
    cx, cy = 400, 320
    p.setBrush(QColor(ear))
    if ear_style == "up":
        for s in (-1, 1):
            path = QPainterPath(QPointF(cx + s * 70, cy - 110)); path.lineTo(cx + s * 185, cy - 230)
            path.lineTo(cx + s * 165, cy - 50); path.closeSubpath(); p.drawPath(path)
    else:
        for s in (-1, 1):
            p.save(); p.translate(cx + s * 150, cy - 40); p.rotate(s * 15)
            p.drawRoundedRect(QRectF(-50, -60, 100, 220 if ear_style == "long" else 160), 50, 50); p.restore()
    ball(p, cx, cy, 165, fur, "#ffffff")
    if spot:
        p.setBrush(QColor(spot)); p.drawEllipse(QRectF(cx + 20, cy - 140, 120, 130))
    p.setBrush(QColor("#fff8ee")); p.drawEllipse(QRectF(cx - 95, cy + 10, 190, 140))
    p.setBrush(QColor("#222"))
    for s in (-1, 1):
        p.drawEllipse(QPointF(cx + s * 62, cy - 30), 18, 20)
    p.setBrush(QColor("#ffffff"))
    for s in (-1, 1):
        p.drawEllipse(QPointF(cx + s * 62 + 6, cy - 37), 6, 6)
    p.setBrush(QColor("#222")); p.drawEllipse(QRectF(cx - 30, cy + 30, 60, 42))
    p.setPen(QPen(QColor("#222"), 5)); p.setBrush(Qt.NoBrush)
    p.drawArc(QRectF(cx - 50, cy + 70, 50, 40), 180 * 16, 180 * 16)
    p.drawArc(QRectF(cx, cy + 70, 50, 40), 180 * 16, 180 * 16)
    p.setPen(Qt.NoPen)
    if tongue:
        p.setBrush(QColor("#f06292")); p.drawRoundedRect(QRectF(cx - 22, cy + 100, 44, 55), 20, 20)


def shiba(p): dog(p, "#e0954a", "#c8752e", "up", tongue=True)
def retriever(p): dog(p, "#f2c97a", "#d9a54e", "floppy", tongue=True)
def husky(p): dog(p, "#9ea7b3", "#6f7884", "up")
def beagle(p): dog(p, "#f3e3cc", "#8a5a2b", "long", spot="#b07238")
def poodle(p): dog(p, "#e9e4dc", "#d8d0c4", "long")


# 파일 이름은 섞어서 번호만 — 이름으로 분류하지 못하게
ITEMS = [
    ("01", "#fff3e0", apple), ("02", "#e3f2fd", car), ("03", "#fffde7", banana),
    ("04", "#fff8e1", bus), ("05", "#f3e5f5", grape), ("06", "#e0f7fa", bicycle),
    ("07", "#fff8e1", orange), ("08", "#e1f5fe", airplane), ("09", "#e0f2f1", watermelon),
    ("10", "#e0f2f1", boat), ("11", "#e3f2fd", shiba), ("12", "#fce4ec", husky),
    ("13", "#fff3e0", beagle), ("14", "#e8eaf6", retriever), ("15", "#f9fbe7", poodle),
]

if __name__ == "__main__":
    app = QGuiApplication([])
    out = HERE / "unsorted"; out.mkdir(exist_ok=True)
    (HERE / "fruit").mkdir(exist_ok=True); (HERE / "vehicle").mkdir(exist_ok=True); (HERE / "dog").mkdir(exist_ok=True)
    for num, bg, fn in ITEMS:
        img, p = canvas(bg); fn(p); p.end()
        img.save(str(out / f"photo_{num}.png"))
    print("saved", len(ITEMS), "→", out)
