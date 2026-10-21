# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 유데브앱 최형선 (UDevApp, HyungSun Choi) — https://udevapp.co.kr
"""세 OS 모듈이 같이 쓰는 기본 구현."""
import os
from pathlib import Path


def sanitize_isdir(path, allow_home: bool = True) -> str:
    """폴더가 있으면 그대로, 없으면 홈(allow_home) 또는 ""."""
    home = str(Path.home())
    if path and os.path.isdir(str(path)):
        return str(path)
    return home if allow_home else ""


def no_op(*_args, **_kwargs):
    return None
