"""投稿の計画(dry-run)と実行。transport に依存しない部分。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from zenn_scrap.model import CommentFile, Scrap
from zenn_scrap.safety import posted_on, validate
from zenn_scrap.transports.base import ScrapRef, Transport


@dataclass
class Plan:
    scrap: Scrap
    create: bool
    sync_settings: bool
    to_post: list[CommentFile]
    held_by_limit: list[CommentFile]
    changed_after_post: list[CommentFile]
    problems: list[str]
    posted_today: int
    limit: int
    notes: list[str] = field(default_factory=list)

    @property
    def has_work(self) -> bool:
        return bool(self.to_post) or self.sync_settings


def make_plan(scrap: Scrap, *, root: Path, limit: int, today: date | None = None) -> Plan:
    files = scrap.comment_files()
    posted = scrap.posted()
    pending = [cf for cf in files if cf.name not in posted]
    changed = [cf for cf in files if cf.name in posted and posted[cf.name].get("sha256") != cf.sha256]

    notes: list[str] = []
    order = [cf.name for cf in files]
    posted_names = [name for name in order if name in posted]
    if pending and posted_names and order.index(pending[0].name) < order.index(posted_names[-1]):
        notes.append(f"{pending[0].name} は投稿済みのファイルより前の番号。末尾に追記される")

    today = today or datetime.now().astimezone().date()
    used = posted_on(root, today)
    remaining = max(limit - used, 0)
    to_post, held = pending[:remaining], pending[remaining:]

    create = scrap.slug is None
    sync_settings = not create and scrap.settings_sha256 != scrap.settings.sha256
    if create and not to_post:
        sync_settings = False

    return Plan(
        scrap=scrap,
        create=create and bool(to_post),
        sync_settings=sync_settings,
        to_post=to_post,
        held_by_limit=held,
        changed_after_post=changed,
        problems=validate(scrap, pending),
        posted_today=used,
        limit=limit,
        notes=notes,
    )


def execute(
    plan: Plan,
    transport: Transport,
    *,
    interval: float = 5.0,
    log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now().astimezone(),
) -> int:
    """計画どおりに送る。1件ごとに meta.yml へ書き戻す。送ったコメント数を返す。

    失敗したら例外(StopPosting)をそのまま上げる。再試行はしない。
    """
    if plan.problems:
        raise ValueError("問題があるので送らない: " + "; ".join(plan.problems))
    scrap = plan.scrap
    settings = scrap.settings
    sent = 0
    queue = list(plan.to_post)

    if plan.create:
        first = queue.pop(0)

        def on_created(ref: ScrapRef) -> None:
            scrap.record_created(ref.slug, ref.id)
            scrap.save()
            log(f"作成: https://zenn.dev/scraps/{ref.slug}")

        result = transport.create_scrap(
            unlisted=scrap.unlisted, settings=settings, first_body=first.body, on_created=on_created
        )
        if result.settings_applied:
            scrap.record_settings(settings)
        scrap.record_comment(
            first,
            comment_slug=result.first_comment.slug,
            comment_id=result.first_comment.id,
            via=transport.name,
            posted_at=now(),
        )
        scrap.save()
        sent += 1
        log(f"投稿: {first.name} -> {result.first_comment.slug}")
        ref = result.scrap
    else:
        ref = ScrapRef(slug=scrap.slug, id=scrap.scrap_id)  # type: ignore[arg-type]
        if plan.sync_settings:
            transport.update_settings(ref, settings)
            scrap.record_settings(settings)
            scrap.save()
            log("設定(title / closed / can_others_post / topics)を反映した")

    for cf in queue:
        if sent or plan.sync_settings:
            sleep(interval)
        comment = transport.post_comment(ref, cf.body)
        scrap.record_comment(cf, comment_slug=comment.slug, comment_id=comment.id, via=transport.name, posted_at=now())
        scrap.save()
        sent += 1
        log(f"投稿: {cf.name} -> {comment.slug}")
    return sent
