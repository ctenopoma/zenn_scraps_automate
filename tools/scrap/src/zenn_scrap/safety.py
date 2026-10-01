"""送信前の検証。Zenn のルールとの照合(zenn_scraps_automate/docs/research/05)で決めた条件を実装する。"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path

from zenn_scrap.model import CommentFile, Scrap, iter_scraps

# サーバー側の制約(https://zenn.dev/openapi.yaml の CreateScrapRequest など)
TITLE_MAX = 100
BODY_MAX = 20_000
TOPICS_MAX = 5

DEFAULT_DAILY_LIMIT = 20

# 送信前の簡易 secret scan。Zenn 本体の検出機能はメール通知だけで公開を止めない。
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern))
    for name, pattern in [
        ("Zenn API キー", r"zenn_api_[A-Za-z0-9_\-]{16,}"),
        ("Zenn のセッション Cookie", r"(?:_zenn_session|remember_user_token)\s*[=:]\s*[A-Za-z0-9%+/=_\-.]{20,}"),
        ("Bearer トークン", r"Bearer\s+[A-Za-z0-9._\-]{24,}"),
        ("AWS アクセスキー", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        ("GitHub トークン", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"),
        ("Anthropic API キー", r"\bsk-ant-[A-Za-z0-9_\-]{20,}"),
        ("OpenAI API キー", r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}"),
        ("Google API キー", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        ("Slack トークン", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
        ("秘密鍵", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    ]
]


def scan_secrets(text: str) -> list[str]:
    return [name for name, pattern in SECRET_PATTERNS if pattern.search(text)]


def validate(scrap: Scrap, files: list[CommentFile]) -> list[str]:
    """投稿を止めるべき問題の一覧。空なら送ってよい。"""
    problems: list[str] = []
    s = scrap.settings
    if not s.title.strip():
        problems.append("meta.yml の title が空")
    if len(s.title) > TITLE_MAX:
        problems.append(f"title が {TITLE_MAX} 文字を超える({len(s.title)} 文字)")
    if len(s.topic_names) > TOPICS_MAX:
        problems.append(f"topic_names が {TOPICS_MAX} 件を超える({len(s.topic_names)} 件)")
    for found in scan_secrets(s.title):
        problems.append(f"title に {found} らしき文字列がある")
    for cf in files:
        if not cf.body:
            problems.append(f"{cf.name}: 本文が空")
        if len(cf.body) > BODY_MAX:
            problems.append(f"{cf.name}: {BODY_MAX} 文字を超える({len(cf.body)} 文字)")
        for found in scan_secrets(cf.body):
            problems.append(f"{cf.name}: {found} らしき文字列がある")
    return problems


def posted_on(root: Path, day: date) -> int:
    """day(ローカル日付)に投稿したコメント数。全スクラップの meta.yml から数える。"""
    count = 0
    for scrap in iter_scraps(root):
        for entry in scrap.posted().values():
            at = entry.get("posted_at")
            if at and datetime.fromisoformat(str(at)).astimezone().date() == day:
                count += 1
    return count


def daily_limit() -> int:
    return int(os.environ.get("ZENN_SCRAP_DAILY_LIMIT", DEFAULT_DAILY_LIMIT))


def refuse_unattended() -> str | None:
    """CI などの無人実行では送信しない(Zenn の AI 方針が懸念する「ボットによる自動運用」を避ける)。"""
    for key in ("CI", "GITHUB_ACTIONS", "BUILD_BUILDID", "JENKINS_URL"):
        if os.environ.get(key):
            return f"環境変数 {key} があるので無人実行とみなし、送信しない"
    return None
