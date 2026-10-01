"""投稿経路(transport)の共通インターフェース。送信部分だけを差し替える。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from zenn_scrap.model import Settings


class StopPosting(Exception):
    """その場で止めるべき応答。POST は再試行しない。"""

    def __init__(self, message: str, *, status: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.detail:
            parts.append(str(self.detail)[:500])
        return " / ".join(parts)


class NotLoggedIn(StopPosting):
    pass


class UnknownResult(StopPosting):
    """送信したが結果を確認できなかった。重複投稿を避けるため再試行しない。"""


@dataclass(frozen=True)
class ScrapRef:
    slug: str
    id: int | None = None


@dataclass(frozen=True)
class CommentRef:
    slug: str
    id: int | None = None


@dataclass(frozen=True)
class CreateResult:
    scrap: ScrapRef
    first_comment: CommentRef
    settings_applied: bool


class Transport(Protocol):
    name: str

    def __enter__(self) -> "Transport": ...

    def __exit__(self, *exc: object) -> None: ...

    def whoami(self) -> str:
        """ログイン中のユーザー名。ログインしていなければ NotLoggedIn。"""
        ...

    def create_scrap(
        self,
        *,
        unlisted: bool,
        settings: Settings,
        first_body: str,
        on_created: Callable[[ScrapRef], None],
    ) -> CreateResult:
        """スクラップを作り、最初のコメントを投稿する。

        on_created はスクラップができた直後に呼ぶ。以降で失敗しても slug を書き戻せるようにするため。
        """
        ...

    def update_settings(self, scrap: ScrapRef, settings: Settings) -> None: ...

    def post_comment(self, scrap: ScrapRef, body: str) -> CommentRef: ...

    def get_comment_markdown(self, comment_slug: str) -> str:
        """投稿済みコメントの Markdown。取得できない transport は NotImplementedError。"""
        ...
