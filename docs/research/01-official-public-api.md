# 01. 公式 Public API（zenn-cli の実験的機能）【第一候補】

調査日: 2026-10-01

## 要旨

- zenn-cli **0.5.3（2026-08-26）以降**に、スクラップを操作する実験的な `zenn scrap` コマンドが入った。
- 認証は **APIキーを `Authorization: Bearer` で送る方式**で、Cookie は使わない。
- 本番の zenn.dev で動いている。API経由で作ったスクラップは `posting_route: "api"` として記録される。
- 以前の「公開しているAPIはありません」（[zenn-community#496](https://github.com/zenn-dev/zenn-community/issues/496)）は、スクラップについては古い情報になった。
- **公式ドキュメントはまだない**。仕様の一次情報は zenn-cli のソースコード。

## 一次情報

- ソース: [zenn-dev/zenn-editor](https://github.com/zenn-dev/zenn-editor)
  - `packages/zenn-cli/src/server/lib/zenn-public-api-client.ts`（v0.5.5-alpha.4 / `e3110d5`）
  - `packages/zenn-cli/src/server/lib/messages.ts`（ヘルプ文言）
- PR: [#697](https://github.com/zenn-dev/zenn-editor/pull/697) / [#698](https://github.com/zenn-dev/zenn-editor/pull/698) / [#711](https://github.com/zenn-dev/zenn-editor/pull/711) / [#712](https://github.com/zenn-dev/zenn-editor/pull/712)
- npm: `latest` は 0.5.4（2026-09-06）、`canary` は 0.5.5-alpha.4（2026-09-28）。2026-10-01 に registry で確認。

## 有効化

```sh
export ZENN_CLI_EXPERIMENTAL_SCRAP_API=true
export ZENN_API_KEY=...   # scrap:read / scrap:write（画像は image:read / image:write）
npx zenn scrap create --title "作業メモ" --file ./scrap.md
npx zenn scrap post <slug> --file - --reply-to <comment_slug>
```

## エンドポイント

ベースURLは `https://zenn.dev/api/public-api/v1`。

| 操作 | メソッド / パス | 主なパラメータ | 成功時 |
|---|---|---|---|
| スクラップ作成（最初のコメント込み） | `POST /scraps` | `title`、`body_markdown`（必須）、`closed`、`archived`、`can_others_post`、`unlisted`、`topic_names[]` | 201 `{"scrap":{"slug","path",...}}` |
| コメント追加 / 返信 | `POST /scraps/{slug}/comments` | `body_markdown`、`parent_comment_slug`（任意。ルートコメントへの返信） | 201 `{"comment":{...}}` |
| 自分のスクラップ一覧 | `GET /scraps?page=&count=` | count は 1〜100 | `{"scraps":[],"next_page"}` |
| スクラップ取得 | `GET /scraps/{slug}?page=&count=` | | `{"scrap":{},"comments":[],"next_page"}` |
| スクラップ更新 | `PATCH /scraps/{slug}` | `title`、`closed`、`archived`、`can_others_post`、`unlisted`、`topic_names` | 200 |
| コメント一括取得 | `GET /comments?slugs[]=...` | 1〜100件 | `{"comments":[],"not_found_slugs":[]}` |
| コメント編集 | `PATCH /scraps/{slug}/comments/{comment_slug}` | `body_markdown` | 200 |
| スクラップ削除（canary） | `DELETE /scraps/{slug}` | アーカイブ済みのもののみ | 204 |
| コメント削除（canary） | `DELETE /scraps/{slug}/comments/{comment_slug}` | 返信も一緒に削除される | 204 |
| 画像アップロード（canary） | `POST /images`（multipart、フィールド名 `file`） | JPEG / PNG / GIF / WebP、3MB以下 | 201 `{"image_url"}` |

- 識別子はすべて slug（文字列）を使う。CLI 側では次の制約で検証している。
  - slug は `^[a-z0-9_-]{12,50}$`
  - 本文は 1MB 以下
- エラーは `{"error":{"code","message"}}` の形で返る。テストに出てくるコードは次のとおり。

| HTTP | code |
|---|---|
| 401 | `invalid_token` |
| 403 | `insufficient_scope` |
| 404 | `not_found` |
| 409 | `image_in_use` |
| 422 | `validation_error` |
| 429 | `rate_limit_exceeded` |
| 500 | `internal_error` |

- CLI は POST / PATCH / DELETE を、ネットワークエラーや 5xx のとき**自動で再試行しない**（重複投稿を防ぐため）。自作するときもこの方針を踏襲する。

## 本番で動いていることの確認（GET のみ）

- 未認証で `GET /api/public-api/v1/scraps` → 401。存在しないパスは 404。つまりエンドポイントは存在し、認証を要求している。
- zenn-cli の開発者のスクラップ [`75fee39cc95c1c`](https://zenn.dev/api/scraps/75fee39cc95c1c)（2026-09-18作成）は、本体もコメント4件もすべて `"posting_route":"api"` だった。
- ブラウザから作ったスクラップは `"posting_route":"web"`。
- **Zenn は API経由の投稿を区別して記録している** → 運営から見て正規の経路で投稿できる。

## 未確認（ログインして確認が必要）

- [ ] APIキーの発行画面。`https://zenn.dev/settings/api-keys` というルートは存在するらしい（200 を返す）。
- [ ] 全ユーザーが発行できるのか、一部のユーザーだけなのか。CLI の 404 メッセージに「この環境またはアカウントではPublic APIを利用できない」とある。
- [ ] キーの有効期限とスコープの選び方。
- [ ] 1日の上限に当たったときのレスポンス（429 なのか別のものか）。
- [ ] レスポンスの `public_api_enabled` フィールドの意味（API で作ったスクラップでも `false` だった）。

## 評価

| 観点 | 評価 |
|---|---|
| 正当性 | ◎ 公式CLIが使う公式経路で、`posting_route: api` として区別される |
| 認証情報のリスク | ○ スコープを絞れて期限もあるAPIキー。Cookie のようにアカウント全権を渡さない |
| 実行時のトークン消費 | ◎ ほぼ0（CLI を1回呼ぶだけ） |
| 壊れやすさ | △ 「実験的機能」なので仕様が変わりうる。ただし公式CLIが追従する |
| CI（GitHub Actions） | ○ APIキーを Secret に入れれば動く。Cookie と違って IP の変化の影響を受けにくいと推測 |
| 実装コスト | ◎ zenn-cli をそのまま使える。足りない部分だけ薄いラッパーを書けばよい |
