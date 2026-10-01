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

調査の過程そのものも、後でスクラップとして投稿する予定。下書きは `scraps/zenn-scrap-automation/001〜009.md`。

## 未決事項（ユーザーに確認すること）

当面の投稿経路をどれにするか。

| 案 | 内容 | 主なトレードオフ |
|---|---|---|
| A | 内部 API + 手動で取得した Cookie（ローカル実行のみ） | すぐ作れる。ただし Cookie が漏れるとアカウント全体を乗っ取られる。非公式なので仕様が変わりうる |
| B | ユーザースクリプトから同一オリジンで fetch | Cookie が外に出ない。ただしブラウザを開いておく必要がある |
| C | Public API の公開を待ち、それまでは手で貼る | リスクはない。自動化はできない |

## 次の作業（A か B に決まった場合）

1. DevTools で、スクラップ作成（`POST /api/scraps`）とコメント投稿（`POST /api/comments`）のリクエストとレスポンスを1回ずつ記録する（Cookie は伏せる）。
   - あわせて確認すること: CSRF や Origin のチェックがあるか、作成時に topics や unlisted を指定できるか。
2. `post` / `verify` の CLI を実装する。言語は未定（Node だと zenn-cli と揃う）。
   - 投稿経路は `transport` インターフェースに分け、`public-api` 版の実装を用意しておく。仕様は `docs/research/01` の表のとおり。
   - 検証には、Cookie が使えれば `GET /api/scraps/{slug}/blob.json` で本文の Markdown を照合する。使えなければ `GET /api/scraps/{slug}` でコメント数と slug を照合する。
3. 限定公開で `scraps/zenn-scrap-automation/` を投稿する（ドッグフーディング）。
4. 日次上限に当たったときのレスポンスを観測して記録する。

## 参考にした一次情報

- zenn-cli の Public API クライアント: `zenn-dev/zenn-editor` リポジトリの `packages/zenn-cli/src/server/lib/zenn-public-api-client.ts`（v0.5.5-alpha.4）
- 内部 API のキャプチャ: https://zenn.dev/katzumi/scraps/a0357c5de7b3ea
- Cookie で読み取るツール: https://github.com/ackkerman/zenn-scrap-to-md
