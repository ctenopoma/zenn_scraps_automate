"""public-api transport を、openapi.yaml どおりに振る舞う模擬サーバー相手に確かめる(本番のキーはまだ発行されない)。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from zenn_scrap.model import Settings
from zenn_scrap.transports.base import NotLoggedIn, StopPosting
from zenn_scrap.transports.public_api import PublicApiTransport

SETTINGS = Settings(title="t", closed=False, can_others_post=False, topic_names=("zenn",))


@pytest.fixture
def server():
    received: list[tuple[str, str, dict | None, str | None]] = []
    responses: dict[tuple[str, str], tuple[int, dict]] = {}

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if length else None
            received.append((self.command, self.path, body, self.headers.get("Authorization")))
            status, payload = responses.get((self.command, self.path), (404, {"error": {"code": "not_found", "message": "x"}}))
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PATCH = _handle

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/public-api/v1"
    yield base, received, responses
    httpd.shutdown()


def test_create_and_post(server):
    base, received, responses = server
    responses[("POST", "/api/public-api/v1/scraps")] = (201, {"scrap": {"slug": "abcdefabcdef01"}, "comment": {"slug": "c1c1c1c1c1c1"}})
    responses[("POST", "/api/public-api/v1/scraps/abcdefabcdef01/comments")] = (201, {"comment": {"slug": "c2c2c2c2c2c2"}})
    t = PublicApiTransport(api_key="zenn_api_test", base_url=base)
    created: list[str] = []
    result = t.create_scrap(unlisted=True, settings=SETTINGS, first_body="hello", on_created=lambda r: created.append(r.slug))
    assert created == ["abcdefabcdef01"] and result.first_comment.slug == "c1c1c1c1c1c1"
    assert t.post_comment(result.scrap, "next").slug == "c2c2c2c2c2c2"

    method, path, body, auth = received[0]
    assert auth == "Bearer zenn_api_test"
    assert body == {
        "title": "t",
        "body_markdown": "hello",
        "closed": False,
        "can_others_post": False,
        "unlisted": True,
        "topic_names": ["zenn"],
    }
    assert received[1][2] == {"body_markdown": "next"}


def test_rate_limit_stops(server):
    base, _, responses = server
    responses[("POST", "/api/public-api/v1/scraps/s/comments")] = (429, {"error": {"code": "rate_limit_exceeded", "message": "x"}})
    t = PublicApiTransport(api_key="k", base_url=base)
    from zenn_scrap.transports.base import ScrapRef

    with pytest.raises(StopPosting) as e:
        t.post_comment(ScrapRef(slug="s"), "x")
    assert e.value.status == 429


def test_invalid_token(server):
    base, _, responses = server
    responses[("GET", "/api/public-api/v1/scraps?count=1")] = (401, {"error": {"code": "invalid_token", "message": "x"}})
    with pytest.raises(NotLoggedIn):
        PublicApiTransport(api_key="k", base_url=base).whoami()
