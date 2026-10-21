#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""ImageManager 아이콘 생성기 — 「사진 → 폴더로 분류」 모티프.

    python3 tools/generate_icon.py   →  imagemanager/icons/icon_<N>.png (16~1024)

그림 정본은 이 파일 하나. 앱(모든 OS)·맥 .icns·리눅스 .desktop 이 이 PNG 를 쓴다.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import QApplication

SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def make_pixmap(size: int) -> QPixmap:
    s = float(size)
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)

    # 바탕 — macOS 식 둥근 사각형, 남색→청록 그라데이션
    bg = QRectF(s * 0.06, s * 0.06, s * 0.88, s * 0.88)
    g = QLinearGradient(bg.topLeft(), bg.bottomRight())
    g.setColorAt(0, QColor("#3b5bdb"))
    g.setColorAt(1, QColor("#12b886"))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(bg, s * 0.2, s * 0.2)

    # 폴더 (오른쪽 아래) — 보낼 곳
    p.setBrush(QColor("#f59f00"))
    tab = QPainterPath()
    tab.addRoundedRect(QRectF(s * 0.66, s * 0.51, s * 0.17, s * 0.10), s * 0.03, s * 0.03)
    p.drawPath(tab)
    p.setBrush(QColor("#ffc94d"))
    p.drawRoundedRect(QRectF(s * 0.46, s * 0.56, s * 0.38, s * 0.28), s * 0.04, s * 0.04)

    # 사진 카드 (왼쪽 위, 살짝 기울임)
    p.save()
    p.translate(s * 0.38, s * 0.38)
    p.rotate(-10)
    card = QRectF(-s * 0.22, -s * 0.19, s * 0.44, s * 0.38)
    p.setBrush(QColor(0, 0, 0, 50))
    p.drawRoundedRect(card.translated(s * 0.012, s * 0.02), s * 0.03, s * 0.03)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(card, s * 0.03, s * 0.03)
    photo = card.adjusted(s * 0.03, s * 0.03, -s * 0.03, -s * 0.03)
    p.setBrush(QColor("#a5d8ff"))
    p.drawRect(photo)
    p.setBrush(QColor("#ffd43b"))
    p.drawEllipse(QPointF(photo.right() - s * 0.08, photo.top() + s * 0.07), s * 0.035, s * 0.035)
    p.setBrush(QColor("#2f9e44"))
    p.drawPolygon(QPolygonF([
        QPointF(photo.left(), photo.bottom()),
        QPointF(photo.left() + photo.width() * 0.38, photo.top() + photo.height() * 0.40),
        QPointF(photo.left() + photo.width() * 0.70, photo.bottom()),
    ]))
    p.setBrush(QColor("#40c057"))
    p.drawPolygon(QPolygonF([
        QPointF(photo.left() + photo.width() * 0.45, photo.bottom()),
        QPointF(photo.left() + photo.width() * 0.72, photo.top() + photo.height() * 0.58),
        QPointF(photo.right(), photo.bottom()),
    ]))
    p.restore()

    # 화살표 (사진 → 폴더)
    if size >= 32:
        pen = QPen(QColor("#ffffff"), max(1.5, s * 0.045), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        arc = QPainterPath(QPointF(s * 0.60, s * 0.24))
        arc.quadTo(QPointF(s * 0.78, s * 0.24), QPointF(s * 0.76, s * 0.42))
        p.drawPath(arc)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygonF([
            QPointF(s * 0.685, s * 0.40), QPointF(s * 0.835, s * 0.40), QPointF(s * 0.76, s * 0.50),
        ]))
    p.end()
    return pix


def main():
    app = QApplication(sys.argv)  # noqa: F841
    here = os.path.dirname(os.path.abspath(__file__))
    outs = [os.path.join(os.path.dirname(here), "imagemanager", "icons")]
    for s in SIZES:
        pix = make_pixmap(s)
        for d in outs:
            pix.save(os.path.join(d, f"icon_{s}.png"), "PNG")
    print("saved", len(SIZES), "sizes →", ", ".join(outs))


if __name__ == "__main__":
    main()
