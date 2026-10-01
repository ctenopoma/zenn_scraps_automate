from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from zenn_scrap.model import Scrap, normalize_body, sha256_text
from zenn_scrap.poster import execute, make_plan
from zenn_scrap.safety import scan_secrets
from zenn_scrap.transports.base import CommentRef, CreateResult, ScrapRef, StopPosting
from zenn_scrap.verify import verify

META = """\
# スクラップ1件分のメタデータ
title: "テスト"
topic_names: [zenn, ai]   # 最大5件
unlisted: true        # 作成時にしか選べない
closed: false
can_others_post: false
# --- 以下は投稿ツールが管理 ---
slug: null
comments: []          # 投稿結果
"""

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.astimezone().date()


def make_repo(tmp_path: Path, bodies: list[str], meta: str = META) -> Path:
    d = tmp_path / "scraps" / "t"
    d.mkdir(parents=True)
    (d / "meta.yml").write_text(meta, encoding="utf-8")
    for i, body in enumerate(bodies, 1):
        (d / f"{i:03d}.md").write_bytes(body.encode("utf-8"))
    return tmp_path


class FakeTransport:
    name = "fake"

    def __init__(self, fail_on_post: int | None = None):
        self.calls: list[tuple] = []
        self.fail_on_post = fail_on_post
        self.posts = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def whoami(self) -> str:
        return "me"

    def create_scrap(self, *, unlisted, settings, first_body, on_created):
        self.calls.append(("create", unlisted, settings.title))
        ref = ScrapRef(slug="scrapslug0001", id=42)
        on_created(ref)
        self.calls.append(("settings", settings.topic_names))
        return CreateResult(scrap=ref, first_comment=self._post(first_body), settings_applied=True)

    def update_settings(self, scrap, settings):
        self.calls.append(("settings", settings.topic_names))

    def post_comment(self, scrap, body):
        return self._post(body)

    def _post(self, body):
        self.posts += 1
        if self.fail_on_post == self.posts:
            raise StopPosting("429", status=429)
        self.calls.append(("post", body))
        return CommentRef(slug=f"comment{self.posts:04d}", id=self.posts)

    def get_comment_markdown(self, slug):
        raise NotImplementedError


def test_normalize_body_crlf_and_trailing():
    assert normalize_body("a\r\nb\r\n\r\n") == "a\nb"
    assert sha256_text(normalize_body("x\r\n")) == sha256_text(normalize_body("x\n"))


def test_dry_run_plan(tmp_path):
    root = make_repo(tmp_path, ["one\n", "two\n"])
    plan = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY)
    assert plan.create and [cf.name for cf in plan.to_post] == ["001.md", "002.md"]
    assert plan.problems == []


def test_execute_writes_back_and_keeps_comments(tmp_path):
    root = make_repo(tmp_path, ["one\r\n", "two\n", "three\n"])
    scrap = Scrap(root / "scraps" / "t")
    t = FakeTransport()
    sent = execute(make_plan(scrap, root=root, limit=20, today=TODAY), t, sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    assert sent == 3
    assert [c[1] for c in t.calls if c[0] == "post"] == ["one", "two", "three"]

    text = (root / "scraps" / "t" / "meta.yml").read_text(encoding="utf-8")
    assert "# スクラップ1件分のメタデータ" in text and "# 最大5件" in text
    reloaded = Scrap(root / "scraps" / "t")
    assert reloaded.slug == "scrapslug0001" and reloaded.scrap_id == 42
    assert reloaded.settings_sha256 == reloaded.settings.sha256
    assert [e["comment_slug"] for e in reloaded.posted().values()] == ["comment0001", "comment0002", "comment0003"]

    # 2回目は何もしない(同じ本文を二度送らない)
    again = make_plan(reloaded, root=root, limit=20, today=TODAY)
    assert not again.has_work


def test_stop_midway_then_resume(tmp_path):
    root = make_repo(tmp_path, ["one", "two", "three"])
    scrap = Scrap(root / "scraps" / "t")
    with pytest.raises(StopPosting):
        execute(make_plan(scrap, root=root, limit=20, today=TODAY), FakeTransport(fail_on_post=2), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    reloaded = Scrap(root / "scraps" / "t")
    assert reloaded.slug == "scrapslug0001"
    assert list(reloaded.posted()) == ["001.md"]

    t = FakeTransport()
    plan = make_plan(reloaded, root=root, limit=20, today=TODAY)
    assert not plan.create and [cf.name for cf in plan.to_post] == ["002.md", "003.md"]
    execute(plan, t, sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    assert ("create", True, "テスト") not in t.calls


def test_settings_resync_when_changed(tmp_path):
    root = make_repo(tmp_path, ["one"])
    scrap = Scrap(root / "scraps" / "t")
    execute(make_plan(scrap, root=root, limit=20, today=TODAY), FakeTransport(), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    meta = root / "scraps" / "t" / "meta.yml"
    meta.write_text(meta.read_text(encoding="utf-8").replace("[zenn, ai]", "[zenn, ai, python]"), encoding="utf-8")
    plan = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY)
    assert plan.sync_settings and not plan.to_post


def test_daily_limit_holds_rest(tmp_path):
    root = make_repo(tmp_path, ["one", "two", "three"])
    scrap = Scrap(root / "scraps" / "t")
    execute(make_plan(scrap, root=root, limit=1, today=TODAY), FakeTransport(), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    plan = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=1, today=TODAY)
    assert plan.to_post == [] and [cf.name for cf in plan.held_by_limit] == ["002.md", "003.md"]
    tomorrow = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=1, today=date(2099, 1, 1))
    assert [cf.name for cf in tomorrow.to_post] == ["002.md"]


def test_changed_after_post_is_not_reposted(tmp_path):
    root = make_repo(tmp_path, ["one", "two"])
    scrap = Scrap(root / "scraps" / "t")
    execute(make_plan(scrap, root=root, limit=20, today=TODAY), FakeTransport(), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    (root / "scraps" / "t" / "001.md").write_text("one edited", encoding="utf-8")
    plan = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY)
    assert not plan.to_post and [cf.name for cf in plan.changed_after_post] == ["001.md"]


def test_secret_blocks_posting(tmp_path):
    key = "ghp_" + "a" * 36
    root = make_repo(tmp_path, [f"token: {key}"])
    plan = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY)
    assert plan.problems and "GitHub トークン" in plan.problems[0]
    with pytest.raises(ValueError):
        execute(plan, FakeTransport(), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)


@pytest.mark.parametrize(
    "text",
    [
        "`Authorization: Bearer zenn_api_...` ヘッダー",
        "export ZENN_API_KEY=...   # zenn_api_... 形式",
        "Cookie 名は `_zenn_session` と `remember_user_token`",
    ],
)
def test_secret_scan_ignores_placeholders(text):
    assert scan_secrets(text) == []


def test_title_and_body_limits(tmp_path):
    meta = META.replace('title: "テスト"', 'title: "' + "あ" * 101 + '"')
    root = make_repo(tmp_path, ["x" * 20_001], meta=meta)
    problems = make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY).problems
    assert any("title" in p for p in problems) and any("20000" in p for p in problems)


def test_verify_against_remote(tmp_path):
    root = make_repo(tmp_path, ["one", "two"])
    scrap = Scrap(root / "scraps" / "t")
    execute(make_plan(scrap, root=root, limit=20, today=TODAY), FakeTransport(), sleep=lambda s: None, now=lambda: NOW, log=lambda m: None)
    scrap = Scrap(root / "scraps" / "t")
    remote = {
        "title": "テスト",
        "unlisted": True,
        "can_others_post": False,
        "topics": [{"name": "ai"}, {"name": "zenn"}],
        "user_id": 1,
        "comments": [
            {"slug": "comment0001", "user_id": 1, "posting_route": "web"},
            {"slug": "othercomment", "user_id": 2, "posting_route": "web"},
            {"slug": "comment0002", "user_id": 1, "posting_route": "web"},
        ],
    }
    assert verify(scrap, remote=remote).passed
    remote["comments"].pop(0)
    assert not verify(scrap, remote=remote).passed


def test_browser_module_imports_and_shape():
    from zenn_scrap.transports.browser import _find_username, _shape, default_profile_dir

    assert _shape({"scrap": {"slug": "x", "id": 1, "topics": [{"name": "a"}]}}) == {
        "scrap": {"slug": "str", "id": "int", "topics": [{"name": "str"}]}
    }
    assert _find_username({"user": {"username": "me"}}) == "me"
    assert default_profile_dir("chrome").name == "profile-chrome"


def test_launch_hint():
    from zenn_scrap.transports.browser import launch_hint

    linux = "chrome-headless-shell: error while loading shared libraries: libnspr4.so: cannot open shared object file"
    assert "install-deps" in launch_hint(linux, "chromium")
    assert "--channel msedge" in launch_hint('Chromium distribution "chrome" is not found at /opt/google/chrome/chrome', "chrome")
    assert "playwright install chromium" in launch_hint("Executable doesn't exist at /home/x/.cache/ms-playwright/...", "chromium")
