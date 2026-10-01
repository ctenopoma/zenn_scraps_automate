"""投稿後の照合。

- 認証なしの GET /api/scraps/{slug} で、タイトル、コメントの slug と並び、posting_route を照合する
- --markdown のときは、ログイン済みの browser transport で GET /api/comments/{slug}/markdown を取り、
  sha256 を meta.yml の記録と手元のファイルの両方と照合する
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from zenn_scrap.model import Scrap, normalize_body, sha256_text
from zenn_scrap.transports.base import Transport

ORIGIN = "https://zenn.dev"


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    ng: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.ng


def fetch_public_scrap(slug: str) -> dict[str, Any]:
    """認証なしで GET /api/scraps/{slug}。コメントはページをたどって全部集める。"""
    comments: list[dict[str, Any]] = []
    scrap: dict[str, Any] = {}
    page: int | None = 1
    while page:
        url = f"{ORIGIN}/api/scraps/{slug}" + (f"?page={page}" if page > 1 else "")
        req = urllib.request.Request(url, headers={"User-Agent": "zenn-scrap verify", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.loads(res.read().decode("utf-8"))
        scrap = data.get("scrap") or {}
        comments.extend(scrap.get("comments") or [])
        page = data.get("next_page") or scrap.get("next_page")
    scrap["comments"] = comments
    return scrap


def verify(scrap: Scrap, *, remote: dict[str, Any], markdown_from: Transport | None = None) -> Report:
    r = Report()
    posted = list(scrap.posted().values())

    if remote.get("title") == scrap.title:
        r.ok.append("title が一致")
    else:
        r.ng.append(f"title が違う: zenn={remote.get('title')!r} / meta={scrap.title!r}")

    if bool(remote.get("unlisted")) == scrap.unlisted:
        r.ok.append(f"unlisted={scrap.unlisted} が一致")
    else:
        r.ng.append(f"unlisted が違う: zenn={remote.get('unlisted')} / meta={scrap.unlisted}")

    if bool(remote.get("can_others_post")) == scrap.settings.can_others_post:
        r.ok.append(f"can_others_post={scrap.settings.can_others_post} が一致")
    else:
        r.ng.append(f"can_others_post が違う: zenn={remote.get('can_others_post')} / meta={scrap.settings.can_others_post}")

    remote_topics = sorted(t.get("name", "") for t in remote.get("topics") or [] if isinstance(t, dict))
    if remote_topics == sorted(scrap.settings.topic_names):
        r.ok.append("topics が一致")
    else:
        r.ng.append(f"topics が違う: zenn={remote_topics} / meta={sorted(scrap.settings.topic_names)}")

    # 自分が投稿したトップレベルのコメントだけを並び順で比べる(他人のコメントや返信は数えない)
    mine = [c for c in remote["comments"] if c.get("user_id") == remote.get("user_id")]
    remote_slugs = [c.get("slug") for c in mine]
    local_slugs = [str(e.get("comment_slug")) for e in posted]
    if remote_slugs == local_slugs:
        r.ok.append(f"コメント {len(local_slugs)} 件の slug と並びが一致")
    else:
        missing = [s for s in local_slugs if s not in remote_slugs]
        extra = [s for s in remote_slugs if s not in local_slugs]
        r.ng.append(f"コメントの slug が違う: zenn にない={missing} / meta にない={extra}")
    routes = sorted({str(c.get("posting_route")) for c in mine})
    r.ok.append(f"posting_route: {', '.join(routes) or '(なし)'}")

    if markdown_from is not None:
        files = {cf.name: cf for cf in scrap.comment_files()}
        for e in posted:
            name, slug = str(e["file"]), str(e["comment_slug"])
            got = sha256_text(normalize_body(markdown_from.get_comment_markdown(slug)))
            if got != e.get("sha256"):
                r.ng.append(f"{name}: zenn の Markdown が送った本文と違う")
            elif name in files and files[name].sha256 != got:
                r.ng.append(f"{name}: 投稿後に手元のファイルが変わっている")
            else:
                r.ok.append(f"{name}: Markdown が一致")
    return r
