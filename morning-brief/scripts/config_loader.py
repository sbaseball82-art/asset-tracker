# -*- coding: utf-8 -*-
"""config.yaml の読み込み（.env があれば環境変数にも反映する）。"""
from __future__ import annotations
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config() -> dict:
    _load_dotenv(os.path.join(ROOT, ".env"))
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_dotenv(path: str) -> None:
    """APIキーは .env 管理（リポジトリにはコミットしない）。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
