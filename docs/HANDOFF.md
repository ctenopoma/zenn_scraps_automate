# 引き継ぎメモ（2026-10-01、Cowork セッションから）

## ここまでの経緯

1. Zenn の方針・規約を確認した → `docs/research/00`
   - スクラップは AI の出力を投稿してよい。ただし1日あたりの上限がある（数値は非公開）。
2. 投稿方式を4系統調べた → `docs/research/01〜03`、比較は `04`
   - 公式 Public API
   - 非公式の内部 API（Cookie を使う）
   - Playwright などのブラウザ自動化
   - 拡張機能
3. zenn-cli 0.5.3 以降に、スクラップ向けの Public API（Bearer 認証）があることを発見した。
   - 本番で動いており、投稿は `posting_route: "api"` として記録される。
4. ところが、ログインした状態でも `https://zenn.dev/settings/api-keys` が 404 だった。
   - 一般ユーザーにはまだ API キーが発行されていない。
   - info.zenn.dev にも告知はない。
5. 方針を見直した。投稿経路を差し替えられる作りにし、当面の経路を決めるところで止まっている。

6. （2026-10-01、Claude Code セッション）経路の決定はユーザーの判断で保留し、調査を続けた。詳細は `docs/research/01` の「追記2」。
   - 発行画面 `/settings/api-keys` は zenn.dev に実在する。ユーザーごとのフラグ `publicApiEnabled` が偽だと、クライアント側で 404 を描画する。
   - 自分でフラグを有効にする UI はない。2026-09 の公開スクラップ 1,440 件のうち、API 経由の投稿は zenn-cli 作者の1件だけ。
   - 公式の OpenAPI 仕様が https://zenn.dev/openapi.yaml で公開されていた。書き込みのスコープは `scrap:write:own`。本文は 20,000 文字まで。日次上限は 429 で返る。GET では `body_html` しか返らない。
   - ユーザーが挙げた記事（t_oishi）は認証なしの読み取り API で、Public API とは別物だった。

調査の過程そのものも、後でスクラップとして投稿する予定。下書きは `scraps/zenn-scrap-automation/001〜010.md`。

## 決まったこと

- CLI の実装言語は **Python（uv）**。依存は `pyproject.toml` に書き、`uv sync` で入れる（`uv pip` は使わない）。

## 未決事項（ユーザーに確認すること）

当面の投稿経路をどれにするか（2026-10-01 時点で保留中。ユーザーは「結論を出さずに調査を続ける」方針）。

| 案 | 内容 | 主なトレードオフ |
|---|---|---|
| A | 内部 API + 手動で取得した Cookie（ローカル実行のみ） | すぐ作れる。ただし Cookie が漏れるとアカウント全体を乗っ取られる。非公式なので仕様が変わりうる |
| B | ユーザースクリプトから同一オリジンで fetch | Cookie が外に出ない。ただしブラウザを開いておく必要がある |
| C | Public API の公開を待ち、それまでは手で貼る | リスクはない。自動化はできない |

## 次の作業（A か B に決まった場合）

1. DevTools で、スクラップ作成（`POST /api/scraps`）とコメント投稿（`POST /api/comments`）のリクエストとレスポンスを1回ずつ記録する（Cookie は伏せる）。
   - あわせて確認すること: CSRF や Origin のチェックがあるか、作成時に topics や unlisted を指定できるか。
2. `post` / `verify` の CLI を Python（uv）で実装する。
   - 投稿経路は `transport` インターフェースに分け、`public-api` 版の実装を用意しておく。仕様の一次情報は https://zenn.dev/openapi.yaml（`docs/research/01` の追記2に要点がある）。
   - 検証には、Cookie が使えれば `GET /api/scraps/{slug}/blob.json` で本文の Markdown を照合する。使えなければ `GET /api/scraps/{slug}` でコメント数と slug を照合する。
3. 限定公開で `scraps/zenn-scrap-automation/` を投稿する（ドッグフーディング）。
4. 日次上限に当たったときのレスポンスを観測して記録する。

## 参考にした一次情報

- Public API の公式仕様: https://zenn.dev/openapi.yaml（2026-10-01 取得、sha256 `d63ae0e2…73c7`）
- 発行画面のゲート: zenn.dev のフロントエンド（buildId `BRabT0L2RKdbXUX9eJb34`）の `/settings/api-keys` のチャンク
- zenn-cli の Public API クライアント: `zenn-dev/zenn-editor` リポジトリの `packages/zenn-cli/src/server/lib/zenn-public-api-client.ts`（v0.5.5-alpha.4）
- 内部 API のキャプチャ: https://zenn.dev/katzumi/scraps/a0357c5de7b3ea
- Cookie で読み取るツール: https://github.com/ackkerman/zenn-scrap-to-md
