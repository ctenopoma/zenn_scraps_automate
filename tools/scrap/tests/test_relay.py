"""relay の JavaScript を Node.js で実行し、模擬 fetch 相手に流れと sha256 の検証を確かめる。"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone

import pytest

from zenn_scrap.model import Scrap
from zenn_scrap.poster import make_plan
from zenn_scrap.relay import next_job, record, to_js

from test_scrap import TODAY, make_repo

NODE = shutil.which("node")

HARNESS = r"""
const responses = %s;
globalThis.location = {origin: "https://zenn.dev"};
globalThis.sessionStorage = {setItem() {}};
const sent = [];
globalThis.fetch = async (url, init = {}) => {
  const method = init.method || "GET";
  const key = method + " " + url;
  sent.push({key, body: init.body ? JSON.parse(init.body) : null});
  const [status, data] = responses[key] || [404, {message: "not found"}];
  return {status, text: async () => JSON.stringify(data)};
};
globalThis.setTimeout = (f) => f();
"""


def run_js(js: str, responses: dict) -> tuple[dict, list]:
    code = HARNESS % json.dumps(responses) + js.replace("\nout;\n", "\n") + "\nconsole.log(JSON.stringify({out, sent}));\n"
    p = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(p.stdout.strip().splitlines()[-1])
    return data["out"], data["sent"]


OK = {
    "GET /api/me": [200, {"current_user": {"username": "me"}}],
    "POST /api/scraps": [201, {"scrap": {"slug": "newslug000001", "id": 77}}],
    "PUT /api/scraps/newslug000001": [200, {"scrap": {"slug": "newslug000001"}}],
    "POST /api/comments": [201, {"comment": {"slug": "cmt000000001", "id": 5}}],
}


@pytest.mark.skipif(NODE is None, reason="node がない")
def test_create_flow_and_record(tmp_path):
    root = make_repo(tmp_path, ["一つ目\r\n", "二つ目"])
    scrap = Scrap(root / "scraps" / "t")
    job = next_job(make_plan(scrap, root=root, limit=20, today=TODAY))
    out, sent = run_js(to_js(job), OK)
    assert "error" not in out, out
    assert [s["key"] for s in sent] == ["GET /api/me", "POST /api/scraps", "PUT /api/scraps/newslug000001", "PUT /api/scraps/newslug000001", "POST /api/comments"]
    assert sent[1]["body"] == {"title": "テスト", "unlisted": True}
    # scrap と topic_names は別々に送る(1回にまとめると topics しか反映されない)
    assert sent[2]["body"] == {"scrap": {"title": "テスト", "closed": False, "can_others_post": False}}
    assert sent[3]["body"] == {"topic_names": ["zenn", "ai"]}
    assert sent[4]["body"] == {"commentable_type": "Scrap", "commentable_id": 77, "body_markdown": "一つ目"}

    assert "sha256" not in out and len(out["sha_prefix"]) == 12  # 全桁は表示で伏せられることがあるので返さない
    record(scrap, out)
    s = Scrap(root / "scraps" / "t")
    assert s.slug == "newslug000001" and s.scrap_id == 77 and list(s.posted()) == ["001.md"]

    job2 = next_job(make_plan(s, root=root, limit=20, today=TODAY))
    assert job2["kind"] == "comment" and job2["file"] == "002.md" and job2["scrap_id"] == 77
    out2, sent2 = run_js(to_js(job2), OK)
    assert sent2[-1]["body"]["body_markdown"] == "二つ目"


@pytest.mark.skipif(NODE is None, reason="node がない")
def test_sha_mismatch_sends_nothing(tmp_path):
    root = make_repo(tmp_path, ["本文"])
    job = next_job(make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY))
    job["body"] = "本文。"  # LLM の転記で1文字変わった想定
    out, sent = run_js(to_js(job), OK)
    assert "sha256" in out["error"] and [s["key"] for s in sent] == ["GET /api/me"]


@pytest.mark.skipif(NODE is None, reason="node がない")
def test_not_logged_in_sends_nothing(tmp_path):
    root = make_repo(tmp_path, ["本文"])
    job = next_job(make_plan(Scrap(root / "scraps" / "t"), root=root, limit=20, today=TODAY))
    out, sent = run_js(to_js(job), {**OK, "GET /api/me": [401, {"message": "ログインしてください"}]})
    assert out["error"] == "ログインしていない" and len(sent) == 1


@pytest.mark.skipif(NODE is None, reason="node がない")
def test_settings_failure_still_records_slug(tmp_path):
    root = make_repo(tmp_path, ["本文"])
    scrap = Scrap(root / "scraps" / "t")
    job = next_job(make_plan(scrap, root=root, limit=20, today=TODAY))
    out, _ = run_js(to_js(job), {**OK, "PUT /api/scraps/newslug000001": [422, {"message": "x"}]})
    assert out["slug"] == "newslug000001" and "PUT" in out["error"]
    record(scrap, out)
    s = Scrap(root / "scraps" / "t")
    assert s.slug == "newslug000001" and not s.posted()
    assert next_job(make_plan(s, root=root, limit=20, today=TODAY))["kind"] == "settings"


def test_record_rejects_sha_mismatch(tmp_path):
    root = make_repo(tmp_path, ["本文"])
    scrap = Scrap(root / "scraps" / "t")
    bad = {"topic": "t", "kind": "create", "slug": "s0000000000001", "scrap_id": 1, "settings_applied": True,
           "file": "001.md", "sha256": "0" * 64, "comment_slug": "c", "comment_id": 1,
           "posted_at": datetime(2026, 10, 2, tzinfo=timezone.utc).isoformat()}
    with pytest.raises(ValueError):
        record(scrap, bad)


@pytest.mark.skipif(NODE is None, reason="node がない")
def test_batch_stops_at_first_error_and_records_rest(tmp_path):
    from zenn_scrap.relay import comment_jobs, record_batch, to_js_batch

    root = make_repo(tmp_path, ["a", "b", "c"])
    scrap = Scrap(root / "scraps" / "t")
    out, _ = run_js(to_js(next_job(make_plan(scrap, root=root, limit=20, today=TODAY))), OK)
    record(scrap, out)
    s = Scrap(root / "scraps" / "t")
    jobs = comment_jobs(make_plan(s, root=root, limit=20, today=TODAY), 10)
    assert [j["file"] for j in jobs] == ["002.md", "003.md"]
    jobs[1]["body"] = "c!"  # 2件目の転記が崩れた想定
    code = HARNESS % json.dumps(OK) + to_js_batch(jobs, 0).replace("({error: stop, results});", "console.log(JSON.stringify({error: stop, results}));")
    p = subprocess.run([NODE, "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8", check=True)
    result = json.loads(p.stdout.strip().splitlines()[-1])
    assert result["results"][0]["comment_slug"] and "sha256" in result["results"][1]["error"]
    assert record_batch(s, result) == ["投稿: 002.md -> cmt000000001"]
    assert list(Scrap(root / "scraps" / "t").posted()) == ["001.md", "002.md"]
