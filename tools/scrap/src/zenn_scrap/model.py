"""scraps/<topic>/ の読み書き。meta.yml のコメント行を残したまま投稿結果を書き戻す。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

COMMENT_FILE_RE = re.compile(r"^\d{3}\.md$")


def normalize_body(text: str) -> str:
    """送信と照合に使う本文の正規形。改行を LF にそろえ、末尾の空白と改行を落とす。

    Windows の作業ツリーは core.autocrlf で CRLF になるため、ハッシュは正規形で取る。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommentFile:
    name: str
    path: Path
    body: str  # normalize_body 済み

    @property
    def sha256(self) -> str:
        return sha256_text(self.body)


@dataclass(frozen=True)
class Settings:
    """作成後にも変更できる設定。unlisted は作成時にしか選べないので含めない。"""

    title: str
    closed: bool
    can_others_post: bool
    topic_names: tuple[str, ...]

    @property
    def sha256(self) -> str:
        payload = {
            "title": self.title,
            "closed": self.closed,
            "can_others_post": self.can_others_post,
            "topic_names": list(self.topic_names),
        }
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _yaml() -> YAML:
    y = YAML()  # round-trip: コメントと並びを保つ
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=2, offset=0)
    return y


class Scrap:
    """scraps/<topic>/ の1件。meta.yml と NNN.md を扱う。"""

    def __init__(self, directory: Path):
        self.dir = directory
        self.meta_path = directory / "meta.yml"
        if not self.meta_path.is_file():
            raise FileNotFoundError(f"{self.meta_path} がない")
        self._yaml = _yaml()
        with self.meta_path.open(encoding="utf-8") as f:
            self.data: CommentedMap = self._yaml.load(f)

    @property
    def topic(self) -> str:
        return self.dir.name

    # --- 人が書く項目 ---
    @property
    def title(self) -> str:
        return str(self.data.get("title") or "")

    @property
    def unlisted(self) -> bool:
        return bool(self.data.get("unlisted", True))

    @property
    def settings(self) -> Settings:
        return Settings(
            title=self.title,
            closed=bool(self.data.get("closed", False)),
            can_others_post=bool(self.data.get("can_others_post", False)),
            topic_names=tuple(str(t) for t in (self.data.get("topic_names") or [])),
        )

    def comment_files(self) -> list[CommentFile]:
        files = sorted(p for p in self.dir.iterdir() if COMMENT_FILE_RE.match(p.name))
        return [
            CommentFile(p.name, p, normalize_body(p.read_text(encoding="utf-8")))
            for p in files
        ]

    # --- ツールが書き戻す項目 ---
    @property
    def slug(self) -> str | None:
        return self.data.get("slug") or None

    @property
    def scrap_id(self) -> int | None:
        value = self.data.get("scrap_id")
        return int(value) if value is not None else None

    @property
    def settings_sha256(self) -> str | None:
        return self.data.get("settings_sha256") or None

    def posted(self) -> dict[str, dict[str, Any]]:
        return {str(c["file"]): c for c in (self.data.get("comments") or [])}

    def _set_after(self, key: str, value: Any, after: str) -> None:
        if key in self.data:
            self.data[key] = value
            return
        keys = list(self.data.keys())
        pos = keys.index(after) + 1 if after in keys else len(keys)
        self.data.insert(pos, key, value)

    def record_created(self, slug: str, scrap_id: int | None) -> None:
        self.data["slug"] = slug
        self._set_after("scrap_id", scrap_id, after="slug")

    def record_settings(self, settings: Settings) -> None:
        self._set_after("settings_sha256", settings.sha256, after="scrap_id")

    def record_comment(
        self,
        cf: CommentFile,
        *,
        comment_slug: str,
        comment_id: int | None,
        via: str,
        posted_at: datetime,
    ) -> None:
        comments = self.data.get("comments")
        if not isinstance(comments, CommentedSeq):
            comments = CommentedSeq(comments or [])
            self.data["comments"] = comments
        comments.fa.set_block_style()
        entry = CommentedMap(
            file=cf.name,
            comment_slug=comment_slug,
            comment_id=comment_id,
            sha256=cf.sha256,
            posted_at=posted_at.isoformat(timespec="seconds"),
            via=via,
        )
        comments.append(entry)

    def save(self) -> None:
        tmp = self.meta_path.with_suffix(".yml.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            self._yaml.dump(self.data, f)
        tmp.replace(self.meta_path)


def find_root(start: Path) -> Path:
    """scraps/ を持つ直近の親ディレクトリ(リポジトリのルート)を探す。"""
    for d in [start, *start.parents]:
        if (d / "scraps").is_dir():
            return d
    # tools/scrap/src/zenn_scrap/model.py から見たリポジトリのルート
    return Path(__file__).resolve().parents[4]


def resolve_scrap(root: Path, topic: str) -> Scrap:
    p = Path(topic)
    directory = p if p.is_dir() else root / "scraps" / topic
    return Scrap(directory)


def iter_scraps(root: Path) -> list[Scrap]:
    base = root / "scraps"
    if not base.is_dir():
        return []
    return [Scrap(d) for d in sorted(base.iterdir()) if (d / "meta.yml").is_file()]
