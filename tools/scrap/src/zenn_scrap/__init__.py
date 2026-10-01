"""scraps/<topic>/ の Markdown を Zenn のスクラップとして投稿・照合する CLI。

Public API(https://zenn.dev/openapi.yaml)が一般ユーザーに開放されるまでの場つなぎとして、
専用プロファイルの Playwright からページ内 fetch で内部 API を呼ぶ transport(browser)を持つ。
"""
