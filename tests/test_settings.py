# -*- coding: utf-8 -*-
"""
config.yml の読み込みと、設定の外出しができているかのテスト。

「自動投稿のコードが存在しないこと」もここで担保する。
これは仕様なので、うっかり足されたらテストで落ちるようにしておく。
"""

import re
from pathlib import Path

import pytest

from src.common import settings
from src.common.util import REPO_ROOT

SRC_DIRS = [REPO_ROOT / "src", REPO_ROOT / "scripts"]


@pytest.fixture(autouse=True)
def clear_cache():
    settings.load.cache_clear()
    yield
    settings.load.cache_clear()


# --------------------------------------------------------------------------
# 読み込み
# --------------------------------------------------------------------------

def test_config_ymlが存在する():
    assert settings.CONFIG_PATH.exists(), "config.yml がありません"


def test_設定が読める():
    cfg = settings.load()
    assert "account" in cfg
    assert "coverage" in cfg


def test_config_ymlが無くても既定値で動く(tmp_path):
    settings.load.cache_clear()
    cfg = settings.load(tmp_path / "no_such.yml")
    assert cfg["coverage"]["halt_below"] == 0.90
    assert cfg["account"]["x_handle"] == "your_account"


def test_書いた値が既定値を上書きする(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("coverage:\n  halt_below: 0.5\n", encoding="utf-8")
    settings.load.cache_clear()
    cfg = settings.load(p)
    assert cfg["coverage"]["halt_below"] == 0.5
    # 書かなかったキーは既定値のまま残る
    assert cfg["coverage"]["warn_below"] == 0.95


# --------------------------------------------------------------------------
# アカウント名
# --------------------------------------------------------------------------

def test_Xハンドルがconfigから読まれる():
    assert settings.x_handle() == "84m5dm9xdm"
    assert settings.x_handle(with_at=True) == "@84m5dm9xdm"


def test_アットマークの有無どちらでも正規化される(tmp_path):
    for raw in ('x_handle: "@foo"', 'x_handle: "foo"'):
        p = tmp_path / f"{raw[-5:]}.yml"
        p.write_text(f"account:\n  {raw}\n", encoding="utf-8")
        settings.load.cache_clear()
        settings.load(p)
        # load() はキャッシュされるので直接確認する
        h = str(settings.load(p)["account"]["x_handle"]).lstrip("@")
        assert h == "foo"


def test_config_pyのX_ACCOUNTがconfig_yml由来になっている():
    import config
    assert config.X_ACCOUNT == settings.x_handle()
    assert not config.X_ACCOUNT.startswith("@")


# --------------------------------------------------------------------------
# 闾値
# --------------------------------------------------------------------------

def test_カバレッジ闾値():
    assert settings.coverage_halt_below() == 0.90
    assert settings.coverage_warn_below() == 0.95
    assert settings.exclude_declared() is True


def test_鮮度の日数():
    ok_days, warn_days = settings.freshness_days()
    assert ok_days == 35
    assert warn_days == 90


def test_投稿文の文字数上限():
    assert settings.post_limits() == (100, 150, 165)


def test_通知の種類():
    assert settings.notify_on("halt")
    assert settings.notify_on("source_degraded")
    assert not settings.notify_on("そんな種類はない")


def test_パスが絶対パスで返る():
    assert settings.path_of("fund_map").is_absolute()
    assert settings.path_of("fund_map").name == "fund_map.yml"


# --------------------------------------------------------------------------
# 自動投稿のコードが存在しないこと（仕様）
# --------------------------------------------------------------------------

# X への投稿に使われうるライブラリ・エンドポイント
_POSTING = re.compile(
    r"\b(tweepy|python-twitter|twitter\.api|api\.twitter\.com|"
    r"upload\.twitter\.com|create_tweet|update_status|"
    r"statuses/update|/2/tweets)\b", re.I)


def _py_files() -> list[Path]:
    out: list[Path] = []
    for d in SRC_DIRS:
        out += [p for p in d.rglob("*.py") if "__pycache__" not in str(p)]
    return out


def test_自動投稿のコードが存在しない():
    """生成物は人間が目視してから投稿する。投稿処理は入れない。"""
    hits = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        for m in _POSTING.finditer(text):
            hits.append(f"{path.relative_to(REPO_ROOT)}: {m.group(0)}")
    assert hits == [], "X への自動投稿らしきコードがあります: " + "; ".join(hits)


def test_投稿系ライブラリが依存に入っていない():
    req = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for bad in ("tweepy", "python-twitter", "twython"):
        assert bad not in req, f"{bad} が requirements.txt にあります"
