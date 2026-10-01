"""browser transport: Zenn 専用プロファイルの Playwright から、zenn.dev のページ内 fetch で内部 API を呼ぶ。

Cookie を取り出さない。ログインは `zenn-scrap login` で人がメール(確認コード)で一度だけ行う。
環境変数 ZENN_SCRAP_TRACE にファイルを指定すると、応答の形(キー名と型、値は残さない)を JSONL で追記する。
呼び方は zenn.dev のフロントエンドの JS から読んだもの(zenn_scraps_automate/docs/research/02 の追記)。
共通の API クライアントは Content-Type: application/json だけを付け、キーを snake_case に変換して送っている。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
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

ORIGIN = "https://zenn.dev"

_FETCH_JS = """
async ({method, path, body}) => {
  const init = {method, credentials: "same-origin", headers: {}};
  if (body !== null) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const r = await fetch(path, init);
  return {status: r.status, text: await r.text()};
}
"""


DEFAULT_CHANNEL = "chrome"


def default_channel() -> str:
    return os.environ.get("ZENN_SCRAP_CHANNEL", DEFAULT_CHANNEL)


def default_profile_dir(channel: str | None = None) -> Path:
    """Zenn 専用のプロファイル。ブラウザごとに分ける(Cookie の暗号化がブラウザごとに違うため)。"""
    env = os.environ.get("ZENN_SCRAP_PROFILE_DIR")
    if env:
        return Path(env)
    name = f"profile-{channel or default_channel()}"
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "zenn-scrap" / name
    return Path.home() / ".local" / "share" / "zenn-scrap" / name


def _shape(value: Any) -> Any:
    """応答の形(キー名と型)だけを取り出す。値は残さない。"""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def launch_hint(message: str, channel: str) -> str:
    """ブラウザを起動できなかったときの対処。Playwright のエラー文から判断する。"""
    if "error while loading shared libraries" in message:
        return ("Linux でブラウザの共有ライブラリが足りない。sudo で "
                "`uv run --project tools/scrap playwright install-deps chromium` を実行するか、"
                "Linux 版の Chrome を入れる")
    if "is not found" in message or "Executable doesn't exist" in message:
        if channel == "chromium":
            return "Playwright の Chromium がない。`uv run --project tools/scrap playwright install chromium` を実行する"
        return f"{channel} が見つからない。インストールするか、`--channel msedge` / `--channel chromium` を使う"
    return "ブラウザのプロファイルを別のブラウザが使っていないか確かめる(同じプロファイルは同時に1つしか開けない)"


def _find_username(data: Any) -> str | None:
    if isinstance(data, dict):
        if isinstance(data.get("username"), str):
            return data["username"]
        for key in ("user", "current_user", "me"):
            found = _find_username(data.get(key))
            if found:
                return found
    return None


def _first(data: Any, key: str) -> dict[str, Any]:
    """{"scrap": {...}} の形でも {...} の形でも中身を返す。"""
    if isinstance(data, dict) and isinstance(data.get(key), dict):
        return data[key]
    if isinstance(data, dict):
        return data
    raise StopPosting(f"想定外の応答({key})", detail=data)


class BrowserTransport:
    name = "browser"
    step_pause = 1.0  # 作成の内部で続けて送るリクエストの間隔(秒)

    def __init__(
        self,
        *,
        profile_dir: Path | None = None,
        channel: str | None = None,
        headless: bool = False,
    ):
        self.channel = channel or default_channel()
        self.profile_dir = profile_dir or default_profile_dir(self.channel)
        self.headless = headless
        trace = os.environ.get("ZENN_SCRAP_TRACE")
        self.trace_path = Path(trace) if trace else None
        self._pw = None
        self._ctx = None
        self.page = None

    # --- ブラウザの起動と終了 ---
    def __enter__(self) -> "BrowserTransport":
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        channel = None if self.channel == "chromium" else self.channel
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(
                str(self.profile_dir), channel=channel, headless=self.headless
            )
        except PlaywrightError as e:
            self._pw.stop()
            self._pw = None
            first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            raise StopPosting(f"ブラウザ({self.channel})を起動できなかった。{launch_hint(str(e), self.channel)}", detail=first) from e
        self.page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        self.page.goto(ORIGIN + "/", wait_until="domcontentloaded")
        return self

    def __exit__(self, *exc: object) -> None:
        from playwright.sync_api import Error as PlaywrightError

        try:
            if self._ctx is not None:
                self._ctx.close()
        except PlaywrightError:
            pass  # 人がウィンドウを閉じたあとは、閉じる対象がない
        finally:
            if self._pw is not None:
                self._pw.stop()

    # --- 呼び出し ---
    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        from playwright.sync_api import Error as PlaywrightError

        try:
            r = self.page.evaluate(_FETCH_JS, {"method": method, "path": "/api" + path, "body": body})
        except PlaywrightError as e:
            if method == "GET":
                raise StopPosting(f"GET {path} に失敗した: {e}") from e
            raise UnknownResult(f"{method} {path} の結果を確認できなかった。zenn.dev で投稿されたかを目で確かめる: {e}") from e
        text = r["text"]
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = text[:500]
        if self.trace_path is not None:
            record = {"method": method, "path": path, "status": r["status"], "request": _shape(body), "response": _shape(data)}
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return int(r["status"]), data

    def _expect(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        status, data = self._call(method, path, body)
        if status == 401:
            raise NotLoggedIn("ログインが切れている。`zenn-scrap login` でログインし直す", status=status, detail=data)
        if not 200 <= status < 300:
            raise StopPosting(f"{method} {path} が失敗した", status=status, detail=data)
        return data

    # --- Transport ---
    def whoami(self) -> str:
        status, data = self._call("GET", "/me")
        if status == 401:
            raise NotLoggedIn("ログインしていない", status=status, detail=data)
        if status != 200:
            raise StopPosting("GET /me が失敗した", status=status, detail=data)
        username = _find_username(data)
        if not username:
            keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
            raise NotLoggedIn("GET /me の応答にユーザー名がない", status=status, detail=keys)
        return username

    def scrap_id(self, slug: str) -> int:
        scrap = _first(self._expect("GET", f"/scraps/{slug}"), "scrap")
        return int(scrap["id"])

    def create_scrap(
        self,
        *,
        unlisted: bool,
        settings: Settings,
        first_body: str,
        on_created: Callable[[ScrapRef], None],
    ) -> CreateResult:
        created = _first(self._expect("POST", "/scraps", {"title": settings.title, "unlisted": unlisted}), "scrap")
        slug = created.get("slug")
        if not isinstance(slug, str):
            raise UnknownResult("POST /scraps の応答に slug がない。zenn.dev のダッシュボードで確かめる", detail=created)
        ref = ScrapRef(slug=slug, id=created.get("id") if isinstance(created.get("id"), int) else None)
        if ref.id is None:
            ref = ScrapRef(slug=slug, id=self.scrap_id(slug))
        on_created(ref)
        time.sleep(self.step_pause)
        self.update_settings(ref, settings)
        time.sleep(self.step_pause)
        comment = self.post_comment(ref, first_body)
        return CreateResult(scrap=ref, first_comment=comment, settings_applied=True)

    def update_settings(self, scrap: ScrapRef, settings: Settings) -> None:
        # scrap と topic_names を1回で送ると topics しか反映されない(2026-10-02 に実測)。
        # 設定画面と同じく、別々のリクエストで送る。
        fields: dict[str, Any] = {
            "title": settings.title,
            "closed": settings.closed,
            "can_others_post": settings.can_others_post,
        }
        if settings.closed:
            fields["closed_at"] = datetime.now(timezone.utc).isoformat()
        self._expect("PUT", f"/scraps/{scrap.slug}", {"scrap": fields})
        time.sleep(self.step_pause)
        self._expect("PUT", f"/scraps/{scrap.slug}", {"topic_names": list(settings.topic_names)})

    def post_comment(self, scrap: ScrapRef, body: str) -> CommentRef:
        scrap_id = scrap.id if scrap.id is not None else self.scrap_id(scrap.slug)
        data = self._expect(
            "POST",
            "/comments",
            {"commentable_type": "Scrap", "commentable_id": scrap_id, "body_markdown": body},
        )
        comment = _first(data, "comment")
        if comment.get("captcha_required") or (isinstance(data, dict) and data.get("captcha_required")):
            raise StopPosting("CAPTCHA を要求された。回避せずに止める", detail=data)
        slug = comment.get("slug")
        if not isinstance(slug, str):
            raise UnknownResult("POST /comments の応答に slug がない。zenn.dev で確かめる", detail=data)
        cid = comment.get("id")
        return CommentRef(slug=slug, id=cid if isinstance(cid, int) else None)

    def get_comment_markdown(self, comment_slug: str) -> str:
        data = self._expect("GET", f"/comments/{comment_slug}/markdown")
        if isinstance(data, str):
            return data
        for candidate in (data, data.get("comment") if isinstance(data, dict) else None):
            if isinstance(candidate, dict) and isinstance(candidate.get("body_markdown"), str):
                return candidate["body_markdown"]
        raise StopPosting("GET /comments/{slug}/markdown の応答に body_markdown がない", detail=data)

    # --- login 用 ---
    def wait_for_login(self, timeout_sec: int = 600, poll_sec: float = 3.0) -> str:
        """人がメール(確認コード)でログインするのを待つ。"""
        self.page.goto(ORIGIN + "/enter", wait_until="domcontentloaded")
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            time.sleep(poll_sec)
            if self.page.is_closed():
                raise NotLoggedIn("ログインの完了前にブラウザが閉じられた")
            try:
                status, data = self._call("GET", "/me")
            except StopPosting:
                continue  # ページ遷移中は evaluate が失敗する
            if status == 200 and _find_username(data):
                return _find_username(data)  # type: ignore[return-value]
        raise NotLoggedIn(f"{timeout_sec} 秒以内にログインが完了しなかった")
