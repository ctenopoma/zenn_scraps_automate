"""投稿経路(transport)。送信部分だけを差し替える。

- browser: 専用プロファイルの Playwright からページ内 fetch(Public API 開放までの場つなぎ)
- public-api: Zenn Public API(Bearer)。開放されたらこちらに切り替える
"""

from __future__ import annotations

from zenn_scrap.transports.base import Transport

NAMES = ("browser", "public-api")


def make_transport(name: str, *, headless: bool = False, channel: str | None = None) -> Transport:
    if name == "browser":
        from zenn_scrap.transports.browser import BrowserTransport

        return BrowserTransport(headless=headless, channel=channel)
    if name == "public-api":
        from zenn_scrap.transports.public_api import PublicApiTransport

        return PublicApiTransport()
    raise ValueError(f"未知の transport: {name}({', '.join(NAMES)} のどれか)")
