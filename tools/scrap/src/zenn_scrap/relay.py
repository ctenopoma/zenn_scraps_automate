"""relay: 普段使いの Chrome(Claude in Chrome 拡張)から送るための、1手ずつの JavaScript を作り、結果を書き戻す。

普段使いのプロファイルは自動操作できない(Chrome 136 以降)ため、送信だけを拡張機能の javascript 実行に任せる。
送る内容と状態は CLI が決める。JavaScript には本文と sha256 を埋め込み、ページ側で sha256 が一致したときだけ送る。
本文が LLM の出力を経由しても、1文字でも変わっていれば送らない。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from zenn_scrap.model import Scrap
from zenn_scrap.poster import Plan

VIA = "chrome-extension"

_JS_COMMON = r"""
const enc = new TextEncoder();
const hex = async (s) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const shape = (v) => Array.isArray(v) ? (v.length ? [shape(v[0])] : []) : (v && typeof v === "object") ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, shape(x)])) : (v === null ? "null" : typeof v);
const call = async (method, path, body) => {
  const init = {method, credentials: "same-origin", headers: {}};
  if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
  const r = await fetch("/api" + path, init);
  const t = await r.text();
  let d = null;
  try { d = t ? JSON.parse(t) : null; } catch { d = t.slice(0, 300); }
  if (r.status < 200 || r.status >= 300) out.trace.push({method, path, status: r.status, response: shape(d)});
  return {status: r.status, data: d, ok: r.status >= 200 && r.status < 300};
};
const out = {topic: job.topic, kind: job.kind, file: job.file || null, sha256: job.sha256 || null, trace: []};
const save = () => sessionStorage.setItem("zenn-scrap:last", JSON.stringify(out));
// scrap と topic_names を1回で送ると topics しか反映されない(2026-10-02 に実測)。設定画面と同じく分けて送る
const putSettings = async (slug) => {
  const a = await call("PUT", "/scraps/" + slug, {scrap: {title: job.settings.title, closed: job.settings.closed, can_others_post: job.settings.can_others_post}});
  if (!a.ok) return a;
  await sleep(1000);
  return await call("PUT", "/scraps/" + slug, {topic_names: job.settings.topic_names});
};
"""

_JS_GUARD = r"""
if (location.origin !== "https://zenn.dev") { out.error = "zenn.dev のタブで実行していない: " + location.origin; }
else {
  const me = await call("GET", "/me");
  if (!me.ok) out.error = "ログインしていない";
  else if (job.body !== undefined && (await hex(job.body)) !== job.sha256) out.error = "sha256 が一致しない(本文が変わっている)。送らない";
}
"""

_JS_CREATE = r"""
if (!out.error) {
  const c = await call("POST", "/scraps", {title: job.settings.title, unlisted: job.unlisted});
  const s = c.data && (c.data.scrap || c.data);
  if (!c.ok || !s || typeof s.slug !== "string") { out.error = "POST /scraps が失敗した"; out.status = c.status; out.detail = c.data; }
  else {
    out.slug = s.slug; out.scrap_id = typeof s.id === "number" ? s.id : null; save();
    await sleep(1000);
    const p = await putSettings(out.slug);
    if (!p.ok) { out.error = "PUT /scraps/{slug} が失敗した"; out.status = p.status; out.detail = p.data; }
    else {
      out.settings_applied = true; save();
      await sleep(1000);
      if (out.scrap_id === null) { const g = await call("GET", "/scraps/" + out.slug); out.scrap_id = g.data && g.data.scrap && g.data.scrap.id; }
      const m = await call("POST", "/comments", {commentable_type: "Scrap", commentable_id: out.scrap_id, body_markdown: job.body});
      const cm = m.data && (m.data.comment || m.data);
      if (!m.ok || !cm || typeof cm.slug !== "string") { out.error = "POST /comments が失敗した"; out.status = m.status; out.detail = m.data; }
      else { out.comment_slug = cm.slug; out.comment_id = typeof cm.id === "number" ? cm.id : null; out.posted_at = new Date().toISOString(); }
    }
  }
}
"""

_JS_SETTINGS = r"""
if (!out.error) {
  const p = await putSettings(job.slug);
  if (!p.ok) { out.error = "PUT /scraps/{slug} が失敗した"; out.status = p.status; out.detail = p.data; }
  else out.settings_applied = true;
}
"""

_JS_COMMENT = r"""
if (!out.error) {
  const m = await call("POST", "/comments", {commentable_type: "Scrap", commentable_id: job.scrap_id, body_markdown: job.body});
  const cm = m.data && (m.data.comment || m.data);
  if (!m.ok || !cm || typeof cm.slug !== "string") { out.error = "POST /comments が失敗した"; out.status = m.status; out.detail = m.data; }
  else { out.comment_slug = cm.slug; out.comment_id = typeof cm.id === "number" ? cm.id : null; out.posted_at = new Date().toISOString(); }
}
"""


def next_job(plan: Plan) -> dict[str, Any] | None:
    """次の1手。送るものがなければ None。"""
    scrap = plan.scrap
    s = scrap.settings
    settings = {
        "title": s.title,
        "closed": s.closed,
        "can_others_post": s.can_others_post,
        "topic_names": list(s.topic_names),
    }
    if plan.create:
        first = plan.to_post[0]
        return {"topic": scrap.topic, "kind": "create", "unlisted": scrap.unlisted, "settings": settings,
                "file": first.name, "sha256": first.sha256, "body": first.body}
    if plan.sync_settings:
        return {"topic": scrap.topic, "kind": "settings", "slug": scrap.slug, "settings": settings}
    if plan.to_post:
        if scrap.scrap_id is None:
            raise ValueError("meta.yml に scrap_id がない。relay ではスクラップの数値 id が必要")
        cf = plan.to_post[0]
        return {"topic": scrap.topic, "kind": "comment", "slug": scrap.slug, "scrap_id": scrap.scrap_id,
                "file": cf.name, "sha256": cf.sha256, "body": cf.body}
    return None


def to_js(job: dict[str, Any]) -> str:
    body = {"create": _JS_CREATE, "settings": _JS_SETTINGS, "comment": _JS_COMMENT}[job["kind"]]
    head = "const job = " + json.dumps(job, ensure_ascii=False) + ";"
    return head + _JS_COMMON + _JS_GUARD + body + "save();\nout;\n"


def record(scrap: Scrap, result: dict[str, Any], *, now: datetime | None = None) -> list[str]:
    """ブラウザから返った結果を検証して meta.yml に書き戻す。書き戻した内容を返す。"""
    if result.get("topic") != scrap.topic:
        raise ValueError(f"別のスクラップの結果: {result.get('topic')}")
    done: list[str] = []
    kind = result.get("kind")
    if kind == "create":
        if scrap.slug:
            raise ValueError(f"meta.yml にはすでに slug がある: {scrap.slug}")
        if result.get("slug"):
            scrap.record_created(str(result["slug"]), result.get("scrap_id"))
            done.append(f"作成: https://zenn.dev/scraps/{result['slug']}")
    elif kind in ("settings", "comment"):
        if not scrap.slug:
            raise ValueError("meta.yml に slug がない")
    else:
        raise ValueError(f"未知の kind: {kind}")

    if result.get("settings_applied"):
        scrap.record_settings(scrap.settings)
        done.append("設定を反映した")

    if result.get("comment_slug"):
        name = str(result.get("file"))
        files = {cf.name: cf for cf in scrap.comment_files()}
        if name not in files:
            raise ValueError(f"{name} がない")
        cf = files[name]
        if name in scrap.posted():
            raise ValueError(f"{name} はすでに投稿済みとして記録されている")
        if result.get("sha256") != cf.sha256:
            raise ValueError(f"{name}: 送った本文の sha256 が手元のファイルと違う")
        at = result.get("posted_at")
        posted_at = datetime.fromisoformat(str(at).replace("Z", "+00:00")).astimezone() if at else (now or datetime.now().astimezone())
        scrap.record_comment(cf, comment_slug=str(result["comment_slug"]), comment_id=result.get("comment_id"), via=VIA, posted_at=posted_at)
        done.append(f"投稿: {name} -> {result['comment_slug']}")
    if done:
        scrap.save()
    return done


def verify_js(scrap: Scrap) -> str:
    """投稿済みコメントの Markdown をページ内で取得し、正規形の sha256 を meta.yml の記録と比べる JavaScript。"""
    items = [{"file": str(e["file"]), "comment_slug": str(e["comment_slug"]), "sha256": str(e["sha256"])} for e in scrap.posted().values()]
    return (
        "const items = " + json.dumps(items, ensure_ascii=False) + ";\n"
        + r"""
const enc = new TextEncoder();
const hex = async (s) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("");
const res = [];
for (const it of items) {
  const r = await fetch("/api/comments/" + it.comment_slug + "/markdown", {credentials: "same-origin"});
  const t = await r.text();
  let d = null; try { d = JSON.parse(t); } catch { d = t; }
  const md = typeof d === "string" ? d : (d && (d.body_markdown ?? (d.comment && d.comment.body_markdown)));
  if (typeof md !== "string") { res.push({file: it.file, status: r.status, ok: false, keys: d && typeof d === "object" ? Object.keys(d) : typeof d}); continue; }
  const norm = md.replace(/\r\n?/g, "\n").replace(/\s+$/, "");
  res.push({file: it.file, status: r.status, ok: (await hex(norm)) === it.sha256});
}
({checked: res.length, ng: res.filter((x) => !x.ok), keys: res.length ? undefined : []});
"""
    )


_JS_BATCH = r"""
const enc = new TextEncoder();
const hex = async (s) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const call = async (method, path, body) => {
  const init = {method, credentials: "same-origin", headers: {}};
  if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
  const r = await fetch("/api" + path, init);
  const t = await r.text();
  let d = null;
  try { d = t ? JSON.parse(t) : null; } catch { d = t.slice(0, 300); }
  return {status: r.status, data: d, ok: r.status >= 200 && r.status < 300};
};
const results = [];
let stop = null;
if (location.origin !== "https://zenn.dev") stop = "zenn.dev のタブで実行していない: " + location.origin;
else { const me = await call("GET", "/me"); if (!me.ok) stop = "ログインしていない"; }
for (let i = 0; i < jobs.length && !stop; i++) {
  const job = jobs[i];
  const out = {topic: job.topic, kind: "comment", file: job.file, sha_prefix: job.sha256.slice(0, 12)};
  if ((await hex(job.body)) !== job.sha256) { out.error = "sha256 が一致しない(本文が変わっている)。送らない"; results.push(out); break; }
  if (i > 0) await sleep(interval_ms);
  const m = await call("POST", "/comments", {commentable_type: "Scrap", commentable_id: job.scrap_id, body_markdown: job.body});
  const cm = m.data && (m.data.comment || m.data);
  if (!m.ok || !cm || typeof cm.slug !== "string") { out.error = "POST /comments が失敗した"; out.status = m.status; out.detail = m.data; }
  else { out.comment_slug = cm.slug; out.comment_id = typeof cm.id === "number" ? cm.id : null; out.posted_at = new Date().toISOString(); }
  results.push(out);
  sessionStorage.setItem("zenn-scrap:last", JSON.stringify(results));
  if (out.error) break;
}
({error: stop, results});
"""


def comment_jobs(plan: Plan, count: int) -> list[dict[str, Any]]:
    """作成と設定の反映が済んでいるときだけ、コメントの job を count 件まで返す。"""
    if plan.create or plan.sync_settings or not plan.to_post:
        return []
    jobs: list[dict[str, Any]] = []
    for cf in plan.to_post[:count]:
        if plan.scrap.scrap_id is None:
            raise ValueError("meta.yml に scrap_id がない")
        jobs.append({"topic": plan.scrap.topic, "file": cf.name, "sha256": cf.sha256,
                     "scrap_id": plan.scrap.scrap_id, "body": cf.body})
    return jobs


def to_js_batch(jobs: list[dict[str, Any]], interval_ms: int = 5000) -> str:
    return ("const jobs = " + json.dumps(jobs, ensure_ascii=False) + ";\n"
            + f"const interval_ms = {int(interval_ms)};\n" + _JS_BATCH)


def record_batch(scrap: Scrap, result: dict[str, Any]) -> list[str]:
    """to_js_batch の結果を書き戻す。sha256 は表示で伏せられることがあるので、先頭12桁で照合する。"""
    done: list[str] = []
    files = {cf.name: cf for cf in scrap.comment_files()}
    posted = scrap.posted()
    for r in result.get("results") or []:
        if not r.get("comment_slug"):
            continue
        name = str(r["file"])
        if r.get("topic") != scrap.topic or name not in files or name in posted:
            raise ValueError(f"記録できない結果: {r}")
        cf = files[name]
        if not cf.sha256.startswith(str(r.get("sha_prefix"))) or len(str(r.get("sha_prefix"))) < 12:
            raise ValueError(f"{name}: 送った本文の sha256 が手元のファイルと違う")
        at = datetime.fromisoformat(str(r["posted_at"]).replace("Z", "+00:00")).astimezone()
        scrap.record_comment(cf, comment_slug=str(r["comment_slug"]), comment_id=r.get("comment_id"), via=VIA, posted_at=at)
        done.append(f"投稿: {name} -> {r['comment_slug']}")
    if done:
        scrap.save()
    return done
