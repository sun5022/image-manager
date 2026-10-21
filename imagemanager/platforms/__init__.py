# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""OS별 차이 — 휴지통 추적·복원, 삭제 확인, 경로 검증, 로그, 앱 이름·아이콘, 네이티브 키.

공통 코드(app.py)는 여기 `current()` 가 돌려준 모듈의 함수만 부른다. 세 모듈은 같은 이름의 함수를 갖는다:

    setup_logging(logger)                 로그 출력 위치
    before_qapp(app_name)                 QApplication 만들기 전 (맥: 메뉴 막대 이름)
    after_qapp(app, icon)                 QApplication 만든 뒤 (맥: Dock 아이콘)
    install_key_monitor(window)           한글 입력 상태 단축키 (맥만 실제 동작)
    sanitize_path(path, allow_home)       저장·인자 경로 검증 (못 쓰면 홈 또는 "")
    confirm_delete(parent, paths) -> bool 삭제 전 확인 (맥: 미리보기 창)
    trash(path) -> str                    휴지통으로 보내고 되돌리기용 표식(못 찾으면 "")
    restore(token, dst)                   표식 → dst 로 되돌림
    CMD_BACKSPACE_DELETE                  Cmd/Ctrl+Backspace = 삭제 (맥 관례)

테스트·점검용: 환경변수 IMGMGR_PLATFORM=mac|linux|windows 로 강제 선택.
"""
import os
import sys


def name() -> str:
    forced = os.environ.get("IMGMGR_PLATFORM")
    if forced in ("mac", "linux", "windows"):
        return forced
    if sys.platform == "darwin":
        return "mac"
    if sys.platform == "win32":
        return "windows"
    return "linux"


def current():
    n = name()
    if n == "mac":
        from . import mac as m
    elif n == "windows":
        from . import windows as m
    else:
        from . import linux as m
    return m
