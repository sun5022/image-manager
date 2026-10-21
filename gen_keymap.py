#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""키보드 배치도 생성기 — images/keymap.png (README·F1 도움말 공용).

키 매핑을 바꾸면 아래 KEYS 표만 고치고 다시 실행한다:
    python3 gen_keymap.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "images" / "keymap.png"

def _first(*paths):
    """리눅스 나눔바른고딕 → 맥 Pretendard 순으로 있는 글꼴."""
    for p in paths:
        if Path(p).expanduser().exists():
            return str(Path(p).expanduser())
    return paths[0]


FONT_B = _first("/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf", "~/Library/Fonts/Pretendard-Bold.otf", "C:/Windows/Fonts/malgunbd.ttf")
FONT_R = _first("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf", "~/Library/Fonts/Pretendard-Regular.otf", "C:/Windows/Fonts/malgun.ttf")

U = 80          # 키 1칸(px)
PAD = 6         # 키 사이 간격
X0, Y0 = 40, 250

# 역할별 색 (배경, 테두리)
ROLE = {
    "src": ("#1e5aa8", "#5b9be6"),   # 왼손 = 왼쪽 소스
    "tgt": ("#2e7d32", "#66bb6a"),   # 오른손 = 오른쪽 타겟
    "act": ("#c25e00", "#ffa040"),   # 보내기 (소스 → 타겟)
    "com": ("#5a5f6a", "#9aa0ab"),   # 공통
    "fs":  ("#5e35b1", "#b388ff"),   # 전체화면 (사진 클릭)
    None:  ("#26282d", "#3a3d44"),   # 미사용
}

# 키 기능: 라벨 → (역할, 설명)
KEYS = {
    "W": ("src", "커서 ↑"), "S": ("src", "커서 ↓"),
    "A": ("src", "상위 폴더"), "D": ("src", "폴더 진입"),
    "Q": ("src", "이전 사진"), "E": ("src", "다음 사진"),
    "C": ("act", "복사"), "Space": ("act", "이동"), "M": ("act", "이동"),
    "↑": ("tgt", "커서 ↑\nShift=패널"), "↓": ("tgt", "커서 ↓\nShift=패널"),
    "←": ("tgt", "상위\nShift=되돌림"), "→": ("tgt", "진입"),
    "PgUp": ("tgt", "패널 ↑"), "PgDn": ("tgt", "패널 ↓"),
    "Backspace": ("tgt", "상위"), "Enter": ("act", "이동 (설정에서\n진입·복사로 변경)"),
    "F1": ("com", "도움말"), "F2": ("com", "이름변경"), "F7": ("com", "새 폴더"),
    "Del": ("com", "휴지통"), "Home": ("com", "필터 해제"), "I": ("com", "EXIF"), "/": ("com", "필터"),
    "Z": ("com", "Cmd/Ctrl+Z\n되돌리기"), "N": ("com", "Shift+N\n새 폴더"),
    # 전체화면 보기 (사진 클릭으로 진입) — ←/→·A/D 는 그대로 이전/다음
    "Tab": ("fs", "전체화면\n정보 보기/안보기"), "`": ("fs", "전체화면\n바 고정"), "Esc": ("fs", "전체화면\n닫기"),
    "V": ("fs", "전체화면\n열기·닫기"), "[": ("fs", "전체화면\n축소"), "]": ("fs", "전체화면\n확대"),
}
for i in range(1, 10):
    KEYS[str(i)] = ("tgt", f"패널 {i}")
    KEYS[f"n{i}"] = ("tgt", f"패널 {i}")

# 키보드 배치: (라벨, x칸, y칸, 폭칸)
LAYOUT = []
def row(y, x, items):
    for it in items:
        lab, w = (it, 1) if isinstance(it, str) else it
        LAYOUT.append((lab, x, y, w))
        x += w

row(0, 0, ["Esc"]); row(0, 2, ["F1", "F2", "F3", "F4"])
row(0, 6.5, ["F5", "F6", "F7", "F8"]); row(0, 11, ["F9", "F10", "F11", "F12"])
row(1.3, 0, ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", ("Backspace", 2)])
row(2.3, 0, [("Tab", 1.5), "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", ("\\", 1.5)])
row(3.3, 0, [("Caps", 1.75), "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", ("Enter", 2.25)])
row(4.3, 0, [("Shift", 2.25), "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", ("Shift", 2.75)])
row(5.3, 0, [("Ctrl", 1.5), ("Alt", 1.5), ("Space", 7), ("Alt", 1.5), ("Ctrl", 1.5)])
# 편집·방향 키
row(1.3, 15.5, ["Ins", "Home", "PgUp"]); row(2.3, 15.5, ["Del", "End", "PgDn"])
row(4.3, 16.5, ["↑"]); row(5.3, 15.5, ["←", "↓", "→"])
# 숫자패드 (내부 라벨 n1~n9)
row(2.3, 19.2, [("n7", 1), ("n8", 1), ("n9", 1)])
row(3.3, 19.2, [("n4", 1), ("n5", 1), ("n6", 1)])
row(4.3, 19.2, [("n1", 1), ("n2", 1), ("n3", 1)])
row(5.3, 19.2, [("n0", 2), ("n.", 1)])

W_TOTAL = int(X0 * 2 + 22.2 * U)
H_TOTAL = int(Y0 + 6.3 * U + 84)


def font(path, size):
    return ImageFont.truetype(path, size)


def main():
    img = Image.new("RGB", (W_TOTAL, H_TOTAL), "#16171b")
    d = ImageDraw.Draw(img)
    f_title, f_sub = font(FONT_B, 34), font(FONT_R, 20)
    f_key, f_desc, f_leg = font(FONT_B, 20), font(FONT_R, 14), font(FONT_B, 19)

    d.text((X0, 24), "image-manager 단축키 (v3)", font=f_title, fill="white")
    d.text((X0, 72), "왼손 = 왼쪽 화면(소스·미리보기)  ·  오른손 = 오른쪽 화면(타겟 폴더)  ·  보내기 = 소스 → Active 타겟",
           font=f_sub, fill="#c8ccd4")

    # 화면 구조 미니 그림
    sx, sy, sw, sh = X0, 112, 520, 110
    d.rounded_rectangle((sx, sy, sx + sw * 0.62, sy + sh), 8, fill=ROLE["src"][0], outline=ROLE["src"][1], width=2)
    d.rounded_rectangle((sx + sw * 0.62 + 6, sy, sx + sw, sy + sh), 8, fill=ROLE["tgt"][0], outline=ROLE["tgt"][1], width=2)
    d.text((sx + 16, sy + 14), "왼쪽: 소스", font=f_leg, fill="white")
    d.text((sx + 16, sy + 44), "미리보기 + 사진 목록", font=f_desc, fill="#e0e6f0")
    d.text((sx + sw * 0.62 + 20, sy + 14), "오른쪽: 타겟", font=f_leg, fill="white")
    d.text((sx + sw * 0.62 + 20, sy + 44), "(1) (2) (3) … 폴더", font=f_desc, fill="#e0f0e0")
    ax = sx + sw * 0.62 - 40
    d.text((ax - 30, sy + 76), "C 복사 / Space·M 이동 →", font=f_desc, fill="#ffd0a0", anchor="ra")

    # 범례
    lx = sx + sw + 50
    for i, (r, name) in enumerate([("src", "소스 조작 (왼손)"), ("act", "보내기"), ("tgt", "타겟 조작 (오른손)"),
                                   ("com", "공통"), ("fs", "전체화면 (사진 클릭)")]):
        x = lx + (i % 3) * 280
        y = sy + 10 + (i // 3) * 50
        d.rounded_rectangle((x, y, x + 34, y + 34), 6, fill=ROLE[r][0], outline=ROLE[r][1], width=2)
        d.text((x + 46, y + 6), name, font=f_leg, fill="white")

    for lab, x, y, w in LAYOUT:
        role, desc = KEYS.get(lab, (None, ""))
        bg, ol = ROLE[role]
        px, py = X0 + x * U, Y0 + y * U
        box = (px + PAD / 2, py + PAD / 2, px + w * U - PAD / 2, py + U - PAD / 2)
        d.rounded_rectangle(box, 8, fill=bg, outline=ol, width=2 if role else 1)
        shown = lab[1:] if lab.startswith("n") and len(lab) <= 2 else lab
        if lab.startswith("n") and len(lab) <= 2:
            shown = lab[1:]
        tc = "white" if role else "#6b6f78"
        d.text((box[0] + 9, box[1] + 6), shown, font=f_key, fill=tc)
        if desc:
            # 설명이 칸보다 넓으면 글꼴을 줄여 맞춘다 (윈도우 malgun 은 나눔보다 넓어 Cmd/Ctrl+Z·Shift=패널이 넘쳤음)
            avail = (box[2] - box[0]) - 12
            fd = f_desc
            for size in (14, 12, 11, 10):
                fd = font(FONT_R, size)
                if max(d.textlength(line, font=fd) for line in desc.split("\n")) <= avail:
                    break
            d.multiline_text((box[0] + 9, box[1] + 34), desc, font=fd, fill="#f0f0f0", spacing=1)

    d.text((X0 + 19.2 * U, Y0 + 1.3 * U + 18), "숫자패드", font=f_desc, fill="#9aa0ab")
    d.text((X0, H_TOTAL - 64),
           "· Shift+숫자 = 그 번호 패널로 바로 이동   · Shift+← = 타겟 파일을 소스로 되돌리기(설정에서 Shift+Backspace · 둘 다)   · Cmd+, = 설정   · 한글 입력 상태에서 글자 키가 안 먹으면 한/영 확인   · 원격(sshfs) 폴더에서는 Del 대신 탈락 폴더로 이동",
           font=f_desc, fill="#9aa0ab")
    d.text((X0, H_TOTAL - 40),
           "· 전체화면(사진 클릭 · V — 폴더면 첫 이미지): ←/→ A/D·휠 이전·다음   · [ ] 축소·확대(드래그 이동)   · 끝에서 = 설정 「전체화면 끝에서」   · Tab 정보   · ` 바 고정   · Esc·V·클릭 닫기",
           font=f_desc, fill="#b388ff")
    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT)
    print(OUT, img.size)


if __name__ == "__main__":
    main()
