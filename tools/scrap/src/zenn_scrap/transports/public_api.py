"""public-api transport: Zenn Public API(Bearer)で送る。

仕様の一次情報は https://zenn.dev/openapi.yaml。2026-10 時点では一般ユーザーにキーが発行されていない
(発行画面がユーザーごとのフラグ publicApiEnabled で隠されている)ため、本番では未検証。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

from zenn_scrap.model import Settings
from zenn_scrap.transports.base import (
    CommentRef,
    CreateResult,
    NotLoggedIn,
    ScrapRef,
    StopPosting,
    UnknownResult,
)

DEFAULT_BASE_URL = "https://zenn.dev/api/public-api/v1"


class PublicApiTransport:
    name = "public-api"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        key = (api_key or os.environ.get("ZENN_API_KEY", "")).strip()
        if not key:
            raise StopPosting("環境変数 ZENN_API_KEY がない")
        self._key = key
        self.base_url = (base_url or os.environ.get("ZENN_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

    def __enter__(self) -> "PublicApiTransport":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._key}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                text = res.read().decode("utf-8")
                return json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(text).get("error", text)
            except ValueError:
                detail = text[:500]
            if e.code == 401:
                raise NotLoggedIn("API キーが無効・失効済み、または利用できないユーザーのもの", status=401, detail=detail) from e
            if e.code >= 500 and method != "GET":
                raise UnknownResult(f"{method} {path} の結果を確認できなかった", status=e.code, detail=detail) from e
            raise StopPosting(f"{method} {path} が失敗した", status=e.code, detail=detail) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if method == "GET":
                raise StopPosting(f"GET {path} に失敗した: {e}") from e
            raise UnknownResult(f"{method} {path} の結果を確認できなかった: {e}") from e

    def whoami(self) -> str:
        data = self._call("GET", "/scraps?count=1")
        scraps = (data or {}).get("scraps") or []
        if scraps and isinstance(scraps[0].get("user"), dict):
            return str(scraps[0]["user"].get("username"))
        return "(API キー)"

    def create_scrap(
        self,
        *,
        unlisted: bool,
        settings: Settings,
        first_body: str,
        on_created: Callable[[ScrapRef], None],
    ) -> CreateResult:
        data = self._call(
            "POST",
            "/scraps",
            {
                "title": settings.title,
                "body_markdown": first_body,
                "closed": settings.closed,
                "can_others_post": settings.can_others_post,
                "unlisted": unlisted,
                "topic_names": list(settings.topic_names),
            },
        )
        scrap, comment = (data or {}).get("scrap") or {}, (data or {}).get("comment") or {}
        if not isinstance(scrap.get("slug"), str) or not isinstance(comment.get("slug"), str):
            raise UnknownResult("POST /scraps の応答に slug がない", detail=data)
        ref = ScrapRef(slug=scrap["slug"])
        on_created(ref)
        return CreateResult(scrap=ref, first_comment=CommentRef(slug=comment["slug"]), settings_applied=True)

    def update_settings(self, scrap: ScrapRef, settings: Settings) -> None:
        self._call(
            "PATCH",
            f"/scraps/{scrap.slug}",
            {
                "title": settings.title,
                "closed": settings.closed,
                "can_others_post": settings.can_others_post,
                "topic_names": list(settings.topic_names),
            },
        )

    def post_comment(self, scrap: ScrapRef, body: str) -> CommentRef:
        data = self._call("POST", f"/scraps/{scrap.slug}/comments", {"body_markdown": body})
        comment = (data or {}).get("comment") or {}
        if not isinstance(comment.get("slug"), str):
            raise UnknownResult("POST /scraps/{slug}/comments の応答に slug がない", detail=data)
        return CommentRef(slug=comment["slug"])

    def get_comment_markdown(self, comment_slug: str) -> str:
        # Public API の Comment は body_html しか返さない(openapi.yaml の components.schemas.Comment)
        raise NotImplementedError("Public API では Markdown を取得できない")
