"""zenn-scrap: scraps/<topic>/ を Zenn のスクラップとして投稿・照合する。

    zenn-scrap login                  専用プロファイルでブラウザを開き、メール(確認コード)でログインする
    zenn-scrap whoami                 ログイン中のユーザー名を表示する
    zenn-scrap post <topic>           送る内容を表示する(dry-run、既定)
    zenn-scrap post <topic> --execute 実際に送る
    zenn-scrap verify <topic>         投稿結果を照合する(--markdown で本文も照合)
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from pathlib import Path

from zenn_scrap.model import find_root, resolve_scrap
from zenn_scrap.poster import Plan, execute, make_plan
from zenn_scrap.safety import daily_limit, refuse_unattended
from zenn_scrap.transports import NAMES, make_transport
from zenn_scrap.transports.base import StopPosting


def _out(msg: str = "") -> None:
    print(msg, flush=True)


def _print_plan(plan: Plan, transport: str) -> None:
    s = plan.scrap
    st = s.settings
    _out(f"スクラップ: {s.topic}  ({s.meta_path})")
    _out(f"  title          : {st.title}")
    _out(f"  topics         : {', '.join(st.topic_names) or '(なし)'}")
    _out(f"  unlisted       : {s.unlisted}   can_others_post: {st.can_others_post}   closed: {st.closed}")
    _out(f"  slug           : {s.slug or '(未作成)'}")
    _out(f"  transport      : {transport}")
    _out(f"  今日の投稿数   : {plan.posted_today} / 上限 {plan.limit}")
    _out()
    if plan.create:
        _out("  - スクラップを作成する(限定公開)" if s.unlisted else "  - スクラップを作成する(公開)")
    if plan.sync_settings:
        _out("  - 設定(title / closed / can_others_post / topics)を反映する")
    for cf in plan.to_post:
        _out(f"  - 投稿: {cf.name}  {len(cf.body):>6} 文字  sha256={cf.sha256[:12]}")
    for cf in plan.held_by_limit:
        _out(f"  - 保留(今日の上限): {cf.name}")
    for cf in plan.changed_after_post:
        _out(f"  ! 投稿後に変更されている(再投稿しない): {cf.name}")
    for note in plan.notes:
        _out(f"  ! {note}")
    for p in plan.problems:
        _out(f"  x {p}")
    if not plan.has_work and not plan.problems:
        _out("  送るものはない")


def _profile_must_be_outside(root: Path, channel: str | None) -> None:
    from zenn_scrap.transports.browser import default_profile_dir

    profile = default_profile_dir(channel).resolve()
    if root.resolve() in [profile, *profile.parents]:
        raise SystemExit(f"ブラウザのプロファイル({profile})がリポジトリの中にある。Cookie をコミットしないよう、外に置く")


def cmd_login(args: argparse.Namespace) -> int:
    from zenn_scrap.transports.browser import BrowserTransport

    _profile_must_be_outside(args.root, args.channel)
    with BrowserTransport(channel=args.channel, headless=False) as t:
        try:
            _out(f"ログイン済み: {t.whoami()}  (プロファイル: {t.profile_dir})")
            return 0
        except StopPosting:
            pass
        _out("開いたブラウザで、メールアドレス(確認コード)でログインしてください。完了を待ちます…")
        _out(f"ログインした: {t.wait_for_login()}  (プロファイル: {t.profile_dir})")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    with make_transport(args.transport, headless=args.headless, channel=args.channel) as t:
        _out(t.whoami())
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    scrap = resolve_scrap(args.root, args.topic)
    limit = args.daily_limit if args.daily_limit is not None else daily_limit()
    plan = make_plan(scrap, root=args.root, limit=limit)
    _print_plan(plan, args.transport)
    if plan.problems:
        _out("\n問題があるので送らない。")
        return 2
    if not plan.has_work:
        return 0
    if not args.execute:
        _out("\ndry-run。内容を確認してから --execute を付けて実行する。")
        return 0
    reason = refuse_unattended()
    if reason:
        _out(f"\n{reason}")
        return 2
    if args.transport == "browser":
        _profile_must_be_outside(args.root, args.channel)

    _out()
    try:
        with make_transport(args.transport, headless=args.headless, channel=args.channel) as t:
            _out(f"ログイン中: {t.whoami()}")
            sent = execute(plan, t, interval=args.interval, log=_out)
    except StopPosting as e:
        _out(f"\n停止: {e}")
        _out("POST は再試行しない。meta.yml には送れた分だけ書き戻してある。")
        return 1
    _out(f"\n{sent} 件を送った。`zenn-scrap verify {scrap.topic}` で照合する。")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from zenn_scrap.verify import fetch_public_scrap, verify

    scrap = resolve_scrap(args.root, args.topic)
    if not scrap.slug:
        _out("まだ作成していない(meta.yml の slug が空)")
        return 2
    try:
        remote = fetch_public_scrap(scrap.slug)
    except urllib.error.HTTPError as e:
        _out(f"GET /api/scraps/{scrap.slug} が HTTP {e.code} を返した(削除された、または slug が違う)")
        return 1
    if args.markdown:
        with make_transport("browser", headless=args.headless, channel=args.channel) as t:
            report = verify(scrap, remote=remote, markdown_from=t)
    else:
        report = verify(scrap, remote=remote)
    _out(f"https://zenn.dev{remote.get('path', '/scraps/' + scrap.slug)}")
    for line in report.ok:
        _out(f"  ok  {line}")
    for line in report.ng:
        _out(f"  NG  {line}")
    return 0 if report.passed else 1


def cmd_relay(args: argparse.Namespace) -> int:
    from zenn_scrap.relay import next_job, to_js

    scrap = resolve_scrap(args.root, args.topic)
    limit = args.daily_limit if args.daily_limit is not None else daily_limit()
    plan = make_plan(scrap, root=args.root, limit=limit)
    err = sys.stderr
    if plan.problems:
        for p in plan.problems:
            print(f"x {p}", file=err)
        return 2
    reason = refuse_unattended()
    if reason:
        print(reason, file=err)
        return 2
    from zenn_scrap.relay import comment_jobs, to_js_batch

    # 作成と設定の反映が済んでいれば、コメントは件数にかかわらずまとめ送りの形式で出す
    # (結果の sha256 は先頭12桁で照合する。全桁は表示で伏せられることがあるため)
    if args.count >= 1:
        jobs = comment_jobs(plan, args.count)
        if jobs:
            print(f"コメント {len(jobs)} 件: {', '.join(j['file'] for j in jobs)}  今日 {plan.posted_today}/{plan.limit}", file=err)
            js = to_js_batch(jobs, int(args.interval * 1000))
            if args.out:
                args.out.write_text(js, encoding="utf-8")
                print(f"JavaScript を書いた: {args.out}", file=err)
            else:
                _out(js)
            return 0
    job = next_job(plan)
    if job is None:
        held = f"(今日の上限で保留: {len(plan.held_by_limit)} 件)" if plan.held_by_limit else ""
        print(f"送るものはない{held}", file=err)
        return 0
    print(f"次の1手: {job['kind']} {job.get('file') or ''}  残り {len(plan.to_post)} 件  今日 {plan.posted_today}/{plan.limit}", file=err)
    js = to_js(job)
    if args.out:
        args.out.write_text(js, encoding="utf-8")
        print(f"JavaScript を書いた: {args.out}", file=err)
    else:
        _out(js)
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    import json

    from zenn_scrap.relay import record

    scrap = resolve_scrap(args.root, args.topic)
    raw = Path(args.result[1:]).read_text(encoding="utf-8") if args.result.startswith("@") else args.result
    result = json.loads(raw)
    from zenn_scrap.relay import record_batch

    lines = record_batch(scrap, result) if "results" in result else record(scrap, result)
    for line in lines:
        _out(line)
    if result.get("error"):
        _out(f"停止: {result['error']}" + (f" / HTTP {result['status']}" if result.get("status") else ""))
        if result.get("detail"):
            _out(f"  {str(result['detail'])[:500]}")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="zenn-scrap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", type=Path, default=None, help="scraps/ を持つリポジトリのルート(既定: カレントから上へ探す)")
    p.add_argument("--channel", default=None, help="ブラウザ: chrome(既定) / msedge / chromium(ZENN_SCRAP_CHANNEL)")
    p.add_argument("--headless", action="store_true", help="ブラウザを画面に出さない")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="専用プロファイルでログインする").set_defaults(func=cmd_login)

    w = sub.add_parser("whoami", help="ログイン中のユーザー名")
    w.add_argument("--transport", choices=NAMES, default=os.environ.get("ZENN_SCRAP_TRANSPORT", "browser"))
    w.set_defaults(func=cmd_whoami)

    post = sub.add_parser("post", help="投稿する(既定は dry-run)")
    post.add_argument("topic", help="scraps/ の下のディレクトリ名、またはそのパス")
    post.add_argument("--execute", action="store_true", help="実際に送る")
    post.add_argument("--transport", choices=NAMES, default=os.environ.get("ZENN_SCRAP_TRANSPORT", "browser"))
    post.add_argument("--daily-limit", type=int, default=None, help="1日に送るコメント数の上限(既定 20、ZENN_SCRAP_DAILY_LIMIT)")
    post.add_argument("--interval", type=float, default=5.0, help="送信の間隔(秒)")
    post.set_defaults(func=cmd_post)

    r = sub.add_parser("relay", help="普段の Chrome(Claude in Chrome)で実行する次の1手の JavaScript を出す")
    r.add_argument("topic")
    r.add_argument("--daily-limit", type=int, default=None)
    r.add_argument("--out", type=Path, default=None, help="JavaScript をファイルに書く(既定は標準出力)")
    r.add_argument("--count", type=int, default=1, help="送るコメントの件数(作成と設定の反映が済んでいるとき)")
    r.add_argument("--interval", type=float, default=5.0, help="まとめて送るときの間隔(秒)")
    r.set_defaults(func=cmd_relay)

    rv = sub.add_parser("relay-verify", help="投稿済みコメントの Markdown を普段の Chrome で照合する JavaScript を出す")
    rv.add_argument("topic")
    rv.set_defaults(func=lambda a: (_out(__import__("zenn_scrap.relay", fromlist=["verify_js"]).verify_js(resolve_scrap(a.root, a.topic))), 0)[1])

    rec = sub.add_parser("record", help="relay の JavaScript が返した結果を meta.yml に書き戻す")
    rec.add_argument("topic")
    rec.add_argument("result", help="結果の JSON。@ファイル名 でファイルから読む")
    rec.set_defaults(func=cmd_record)

    v = sub.add_parser("verify", help="投稿結果を照合する")
    v.add_argument("topic")
    v.add_argument("--markdown", action="store_true", help="ログインして Markdown も照合する")
    v.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    args.root = (args.root or find_root(Path.cwd())).resolve()
    try:
        return int(args.func(args))
    except StopPosting as e:
        _out(f"停止: {e}")
        return 1
