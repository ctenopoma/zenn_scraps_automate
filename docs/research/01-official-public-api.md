# 01. 公式 Public API（zenn-cli の実験的機能）【将来の本命／2026-10-01 時点で一般ユーザーは利用不可】

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
export ZENN_API_KEY=...   # zenn_api_... 形式。scrap:read / scrap:write:own（画像は image:read / image:write）
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

- [x] APIキーの発行画面 → **ログインした状態で `https://zenn.dev/settings/api-keys` を開くと 404**（2026-10-01、本人のアカウントで確認）。~~未ログインで 200 が返ったのは誤検知だったとみられる。~~ → 404 はクライアント側で描画しているので、HTTP ステータスは常に 200 になる（下の「追記2」を参照）。
- [x] 全ユーザーが発行できるのか、一部のユーザーだけなのか → **ユーザーごとのフラグ `publicApiEnabled` で開放している**（追記2）。
- [x] キーの有効期限とスコープの選び方 → 発行フォームで、名前・有効日数・スコープを選ぶ（追記2）。
- [x] 1日の上限に当たったときのレスポンス → OpenAPI 上は **429**（「レート制限または投稿数の上限を超えた」）。実物はまだ観測していない。
- [ ] レスポンスの `public_api_enabled` フィールドの意味。2026-09 に作られた公開スクラップ 1,440 件すべてで `false` だった（API で作られた1件も含む）。少なくとも「API で投稿されたか」を表すものではない。

## 2026-10-01 追記: 一般ユーザーにはまだ提供されていない

- ログインした状態でも、APIキーの発行画面（`/settings/api-keys`）は 404 だった。
- [info.zenn.dev](https://info.zenn.dev/) のお知らせとリリースノートには、Public API や APIキーの告知がない（2026-07 以降を確認）。
- zenn-cli の PR（#697 / #711 / #712）にも、提供範囲（一般公開かベータか）や、キーの発行手順は書かれていない。
- 【推測】API 自体は本番で動いているが、キーを発行できるのは運営側か一部のアカウントに限られている。段階的に公開する前の検証期間とみられる。
  - PR の作者は `cm-dyoshikawa`。
  - Zenn の運営会社はクラスメソッド。
- **結論: 当面はこの経路を使えない。** ただし将来の本命なので、ツールは「投稿経路を差し替えられる」作りにしておく（04 参照）。

## 2026-10-01 追記2: 発行画面はユーザーごとのフラグで隠されている

「API を使えている人もいるのでは」という指摘を受けて、追加で調べた。指摘の記事は [t_oishi「Zennの記事をAPIで取得してみよう」](https://zenn.dev/t_oishi/articles/e36041d3af5ea9)（2025-07-25）。この記事が使っているのは認証なしの読み取り API（`/api/articles?username=...`、`/api/users/...`）で、02 で扱っている内部 API の仲間だった。Bearer キーが必要な Public API とは別物。

### 発行画面の正体（zenn.dev のフロントエンドから確認）

- 【事実】zenn.dev のページ一覧に `/settings/api-keys` がある。
  - 出典: https://static.zenn.studio/_next/static/BRabT0L2RKdbXUX9eJb34/_buildManifest.js（buildId `BRabT0L2RKdbXUX9eJb34`、2026-10-01 取得。チャンク名はデプロイごとに変わる）
- 【事実】このページは、ログイン中のユーザーの `publicApiEnabled` が偽のとき、404 のエラー画面を描画する。
  - 出典: 同 buildId のチャンク `static/chunks/19388v3ggxjby.js`。該当箇所は `if(!n.publicApiEnabled){ … ErrorContent,{noindex:!0,statusCode:404} … }`。
  - クライアント側で描画するので、HTTP のステータスは 200 のまま。前回「未ログインで 200」が返ったのはこのため。
- 【事実】設定画面のタブ「APIキー」も、`publicApiEnabled` が真のときだけ表示される（`static/chunks/09erhkg20pl_s.js` の `SettingsLayout`）。
- 【事実】設定画面に、このフラグを自分で有効にする UI は見当たらない（`/settings/account` のチャンクにも、`publicApiEnabled` を参照する箇所は上のタブ表示しかない）。
- 【事実】発行フォームの中身（`19388v3ggxjby.js`）:
  - API: 一覧は `GET /me/api_keys`、発行は `POST /me/api_keys`（`{name, expiresInDays, scopes}`）、失効は `DELETE /me/api_keys/{id}`。いずれも API クライアントからの相対パス。【推測】実体は `/api/me/api_keys`。
  - スコープ: `scrap:read`（Scrapの読み取り）、`scrap:write:own`（Scrapの書き込み（自分のリソース））、`image:read`、`image:write`。
    - `image:read` の注記: 「2022年3月18日以降にZennのサイトまたは公開APIからアップロードした画像が対象です」。
  - 発行するには再認証が必要（「APIキーを発行するには再認証が必要です」）。
  - キーは発行時に1回だけ表示される（「このAPIキーは再表示できません」「チャット、コマンド引数、リポジトリへ貼り付けないでください」）。
  - 画面から `/openapi.yaml` を開ける（「API仕様（OpenAPI）を見る」）。

### 公式の OpenAPI 仕様が公開されている

- 【事実】https://zenn.dev/openapi.yaml は認証なしで取得できる（2026-10-01 取得、27,152 bytes、sha256 `d63ae0e2cb8fb516f4dd8d2966ed59e1fa168e6176152fc68e1762ba7f9873c7`）。`info.title: Zenn Public API`、`version: 1.0.0`。
  - zenn-cli のソースより上位の一次情報になる。上のエンドポイント表は、これと照合して食い違いがなかった。ただし次の点はこちらで補う。
- キーは `Authorization: Bearer zenn_api_...` の形式（`securitySchemes.BearerAuth`）。
- **書き込みに必要なスコープは `scrap:write:own`**。zenn-cli のヘルプには `scrap:write` と書かれているが、OpenAPI と発行画面はどちらも `scrap:write:own`。
- **429** は「レート制限**または投稿数の上限**を超えた」。作成（`POST /scraps`）の説明にも「投稿数の上限に達している場合は429を返します」とある。日次上限は 429 で返ると読める。
- **404** は「リソースが見つからない、**または公開APIを利用できない**」。**401** は「APIキーがない、無効、失効済み、**または利用できないユーザーのもの**」。
- コメント投稿の 403 には「コメント数の上限」が含まれる。1スクラップあたりのコメント数に上限がある。
- `count` の既定値は 50、最大は 100。
- 入力の制約（`CreateScrapRequest` など）:
  - `title` は 100 文字まで。
  - `body_markdown` は **1〜20,000 文字**。zenn-cli は「1MB 以下」で検証しているが、サーバーの制約はこちら。
  - `can_others_post` の既定値は **true**。他人に書き込ませないなら、明示的に false を送る。
  - `unlisted` の既定値は false。
- **取得系（`GET /scraps/{slug}` など）の `Comment` は `body_html` しか返さない。** `body_markdown` は返らない。
  - 【推測】したがって Public API を使っても、投稿後に Markdown で照合することはできない。検証は「コメント数、slug、`posting_route` の一致」と「送った本文の sha256 を手元に記録しておく」の組み合わせになる。

### 運営以外に使っている人はいるか

- 【事実】`GET https://zenn.dev/api/scraps?order=latest&page=1..30` で、公開スクラップ 1,440 件を調べた（2026-09-01〜10-01 に作られたもの、433 ユーザー）。`posting_route` が `api` だったのは 1 件だけ（`dyoshikawa` の [`75fee39cc95c1c`](https://zenn.dev/api/scraps/75fee39cc95c1c)。zenn-cli の PR 作者）。`last_comment_posting_route` が `api` だったのも同じ 1 件。
  - この方法では、限定公開のスクラップや、古いスクラップに API でコメントだけ足した場合は見えない。
- 【事実】GitHub のコード検索で `ZENN_CLI_EXPERIMENTAL_SCRAP_API`、`public-api/v1/scraps`、`zenn scrap create` を検索すると、`zenn-dev/zenn-editor` しかヒットしない（2026-10-01）。
- 【事実】Web 検索でも、第三者が Public API のキーを発行・利用したという報告は見つからなかった。
- 【事実】Zenn は過去にも段階的に機能を開放している。記事の AI レビューは、2025-08-20 のベータで「個人ユーザーについては、一部の方から先行して機能開放しています」とし（https://info.zenn.dev/2025-08-20-ai-review ）、2025-12-03 に全ユーザーへ開放した（https://info.zenn.dev/2025-12-03-ai-review-open-to-all ）。
- 【推測】Public API も同じ流れで、まず運営と一部のユーザーにフラグを立てている段階にあるとみられる。外部のユーザーに開放されているかどうかは、公開情報からは確認できない。
- 【推測】フラグが立てば、設定画面に「APIキー」タブが現れる。これが一番手軽な監視の目印になる。

### zenn-cli 0.5.5-alpha の、投稿前の安全装置

- 【事実】`zenn scrap create` / `post` には次の安全装置がある（`packages/zenn-cli/src/server/lib/messages.ts`、v0.5.5-alpha.4）。
  - Secret scan: 既定で有効。スキップするには `--dangerously-skip-secret-scan` が必要。
  - AI scan: `ZENN_CLI_AI_SCAN=true` のときだけ有効。OpenAI か Fireworks に本文を送って審査させる。
  - `ZENN_CLI_FORCE_UNLISTED=true`: 作成を常に限定公開にする。
  - `ZENN_CLI_FORCE_SAFE=true`: scan のスキップを禁止する。
- 【事実】Zenn 本体にも、2026-09-17 にシークレット検出機能が入った。対象はスクラップのタイトルとコメント本文を含む。ただし「投稿時に公開を止める機能ではありません」で、検出するとメールで通知するだけ（https://info.zenn.dev/2026-09-17-content-secret-detection ）。
- 【推測】自作の CLI でも、送信の前に同じような secret scan を挟むべき。Zenn 側は止めてくれない。

## 評価

| 観点 | 評価 |
|---|---|
| 正当性 | ◎ 公式CLIが使う公式経路で、`posting_route: api` として区別される |
| 認証情報のリスク | ○ スコープを絞れて期限もあるAPIキー。Cookie のようにアカウント全権を渡さない |
| 実行時のトークン消費 | ◎ ほぼ0（CLI を1回呼ぶだけ） |
| 壊れやすさ | △ 「実験的機能」なので仕様が変わりうる。ただし公式CLIが追従する |
| CI（GitHub Actions） | ○ APIキーを Secret に入れれば動く。Cookie と違って IP の変化の影響を受けにくいと推測 |
| 実装コスト | ◎ zenn-cli をそのまま使える。足りない部分だけ薄いラッパーを書けばよい |
