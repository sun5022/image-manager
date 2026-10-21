#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""ImageManager — 모든 OS 공통 진입점.  python image_manager.py [폴더|파일] [-t 타겟 ...]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from imagemanager.app import main  # noqa: E402

if __name__ == "__main__":
    main()
