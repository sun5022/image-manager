#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""ImageManager 진입점 — 코드 본체는 `../imagemanager/` (맥·리눅스·윈도우 공통 한 벌, 0.6.0~).

이 파일은 예전 실행 명령·빌드 설정(.spec)·리눅스 .desktop·윈도우 실행 방법을 그대로 쓰려고 남긴 것.
OS는 실행 환경에서 자동으로 고른다(강제: 환경변수 IMGMGR_PLATFORM=mac|linux|windows).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from imagemanager.app import main  # noqa: E402

if __name__ == "__main__":
    main()
