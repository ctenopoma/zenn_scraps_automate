# 02. 非公式 内部API（Cookie認証）【代替案】

調査日: 2026-10-01

zenn.dev のフロントエンドが内部で呼んでいる API を、ブラウザのセッション Cookie で直接叩く方法。01 の Public API が使えない場合の代替案として調べた。

## エンドポイント

出典: [katzumi「zenn.devのAPIをテストする」](https://zenn.dev/katzumi/scraps/a0357c5de7b3ea)。2023-11 にキャプチャされたもので、現在も同じとは限らない。

| 操作 | リクエスト |
|---|---|
| スクラップ作成 | `POST /api/scraps` `{"title":"..."}` |
| コメント投稿 | `POST /api/comments` `{"commentable_type":"Scrap","commentable_id":<数値id>,"body_markdown":"..."}` |
| 返信 | 上のコメント投稿に `"parent_id":<ルートコメントの数値id>` を追加する |
| アーカイブ | `PUT /api/scraps/{slug}` `{"scrap":{"archived":true}}` |
| 削除 | `DELETE /api/scraps/{slug}` |

- 識別子は、作成・コメントでは**数値id**、PUT・DELETE では**slug**と混在している。
- スクラップの数値idは `GET /api/scraps/{slug}` の `.id` で取得できる。
- キャプチャには `x-` で始まるヘッダも CSRF トークンも写っていなかった。
  - 付いていたヘッダは `origin: https://zenn.dev`、`referer`、`sec-fetch-site: same-origin`、cookie。

## 認証

- Cookie 名は `_zenn_session` と `remember_user_token`（[moxakの記事](https://zenn.dev/moxak/articles/4f695c08676d0a)、[zenn-scrap-to-md](https://github.com/ackkerman/zenn-scrap-to-md)）。
- バックエンドは Rails + Devise。Cookie は http-only・SameSite=Lax（[catnose99、2020](https://zenn.dev/catnose99/scraps/468bedaab6dbe3ecfcae)）。
- セッションの寿命は不明。Devise の既定値は `remember_for = 2.weeks` だが、Zenn がどう設定しているかは分からない。
- ログイン方式は **Google** と **メール（確認コード）** の2つで、GitHub ログインはない（https://zenn.dev/enter 、https://info.zenn.dev/2024-09-10-email-login ）。
  - Google ログインの自動化は、Google のアンチボット対策で事実上できない（03 参照）。
  - したがって Cookie は**人が手動で取得して渡す**運用になる。

## 読み取り（検証用、GETのみで確認）

| エンドポイント | 認証 | 内容 |
|---|---|---|
| `GET /api/scraps/{slug}` | 不要 | `id`、`slug`、`title`、`closed`、`unlisted`、`posting_route`、`comments[]`（**`body_html` のみ**）など |
| `GET /api/scraps?username=...&order=latest` | 不要 | `{"scraps":[...],"next_page"}` |
| `GET /api/scraps/{slug}/blob.json` | **必要** | `{title, comments:[{body_markdown, children}]}`。投稿後に Markdown を照合するのに使える |

## 先行事例

- [ackkerman/zenn-scrap-to-md](https://github.com/ackkerman/zenn-scrap-to-md)（Rust）: `blob.json` を Cookie 付きで取得して Markdown に変換する。**読み取り専用**。
- 内部APIでスクラップを**投稿する**公開ツールは、GitHub でも Qiita でも見つからなかった。

## 未確認（DevTools でキャプチャが必要）

- [ ] POST `/api/scraps` と POST `/api/comments` のレスポンスの形
- [ ] 作成時に topics・closed・unlisted を指定できるか
- [ ] コメントを編集・削除するエンドポイント
- [ ] 2026年現在、Origin や CSRF のチェックがあるか
- [ ] `comment_captcha_enabled` が有効になる条件

## メリット / デメリット

**メリット**
- ブラウザが不要で、実行が速い（数秒）。
- 実行時のLLMトークン消費はほぼ0。
- 本文をファイルからそのまま送るので、内容がずれない。

**デメリット**
- **非公式**。予告なく変わりうる（規約第18条）。公式の Public API ができた今、わざわざこちらを使う理由は薄い。
- **Cookie はアカウント全権に等しい**。漏れると乗っ取られる。スコープも期限も自分では制御できない。
- セッションが切れたら、人が Cookie を取り直す必要がある。寿命は不明。
- CI で使う場合、自宅の IP で発行したセッションをデータセンターの IP から使うことになる。異常検知に引っかかる可能性がある（推測）。
- （推測）運営からは `posting_route: "web"` と記録され、人のブラウザ操作と見分けがつかないはず。「ボットによる自動運用」への懸念を考えると、Public API よりグレー。
