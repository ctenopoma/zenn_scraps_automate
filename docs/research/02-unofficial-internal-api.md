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

## 2026-10-01 追記: フロントエンドの JS から読んだ現在の呼び出し方

- 出典: zenn.dev のフロントエンド（buildId `BRabT0L2RKdbXUX9eJb34`）のうち、`/scraps/new` と `/[username]/scraps/[slug]` のチャンク（`3psinjo1c1dp1.js`、`2qktqgexvxbeg.js`、`409cpvlal7c8i.js`、`32yrit7isvjy9.js`）。2026-10-01 に取得した。GET でコードを読んだだけで、実際には送信していない。
- 【事実】共通の API クライアントが付けるヘッダは `Content-Type: application/json` だけ。CSRF トークンのヘッダは付けていない。
  - 送信時には、本文のキーを camelCase から snake_case に変換している（`bodyMarkdown` → `body_markdown`）。
- 【事実】呼び出し（パスは API クライアントからの相対。【推測】実体は `/api` の下）

| 操作 | リクエスト（snake_case に変換した後） |
|---|---|
| スクラップ作成 | `POST /scraps` `{"title", "unlisted"}`。**作成時に unlisted を指定できる**。topics は作成時には送らない |
| 設定と topics の更新 | `PUT /scraps/{slug}` `{"scrap": {...}, "topic_names": [...]}`。topics だけなら `{"topic_names": [...]}` |
| コメント投稿 | `POST /comments` `{"commentable_type": "Scrap", "commentable_id": <スクラップの数値id>, "body_markdown", "captcha_token"?}` |
| 返信 | 同じく `POST /comments` に `"parent_id": <親コメントの数値id>` を加える |
| コメントの Markdown 取得 | `GET /comments/{slug}/markdown` |
| コメント編集 | `PUT /comments/{slug}` `{"comment": {"body_markdown"}}` |
| コメント削除 | `DELETE /comments/{slug}` |
| スクラップ削除 | `DELETE /scraps/{slug}` |
| 自分のスクラップ一覧 | `GET /me/scraps?page=&keyword=&status=&order=` |

- 【事実】コメントの CAPTCHA は、`scrap.commentCaptchaEnabled` が真で、**かつ自分のスクラップではない**ときだけ要求される（`commentCaptchaRequired = !!(scrap.commentCaptchaEnabled && currentUser.id !== scrap.userId)`）。自分のスクラップに投稿するなら関係ない。
- 【推測】`GET /comments/{slug}/markdown` を使えば、コメント単位で Markdown を照合できる。Public API は `body_html` しか返さないので、検証についてはこちらのほうが強い。

## 2026-10-02 追記: 実際に投稿して観測した応答

`scraps/zenn-scrap-automation`（`C:\work_space\zenn`）を限定公開で投稿したときに観測した（スクラップ `cf27fd4f854925`、コメント 12 件）。送信は、普段使いの Chrome の zenn.dev タブで、Claude in Chrome 拡張から fetch を実行した。応答はキー名と型だけを記録し、値は残していない。

- 【事実】`GET /api/me`: ログイン中は 200 `{"current_user": {...}}`。`current_user` には `username`、`public_api_enabled`（boolean）、`secret_detection_enabled`、`sign_in_types` などが入る。未ログインでは 401 `{"message": "ログインしてください"}`。
- 【事実】`POST /api/scraps` `{"title", "unlisted": true}`: **200**（201 ではない）`{"scrap": {"id", "slug", "path", "title", "unlisted", "can_others_post", "closed", "posting_route", "public_api_enabled", ...}}`。
- 【事実】`PUT /api/scraps/{slug}` に `{"scrap": {...}, "topic_names": [...]}` を**まとめて**送ると、200 `{"topics": [...]}` が返り、**topics だけが反映される**。`scrap` 側の `can_others_post: false` は無視された（作成直後の既定値 true のまま）。
  - `{"scrap": {"title", "closed", "can_others_post"}}` を**単独で**送ると 200 `{"message"}` が返り、反映された。
  - 設定画面のフロントエンドも、scrap の設定と topics を別々のリクエストで送っている。ツールもそれに合わせた。
  - 投稿後の照合（`verify`）で `can_others_post` の不一致として見つかった。
- 【事実】`POST /api/comments` `{"commentable_type": "Scrap", "commentable_id", "body_markdown"}`: **200** `{"comment": {"id", "slug", "body_html", "posting_route", "children", "user", "user_id", ...}}`。
- 【事実】`GET /api/comments/{slug}/markdown`: 200 `{"body_markdown"}`。12 件すべてで、送った本文（改行を LF にそろえて末尾の空白を落とした形）と sha256 が一致した。
- 【事実】投稿したコメントの `posting_route` はすべて `web`。
- 【事実】自分のスクラップへのコメントで、CAPTCHA は要求されなかった。

## 未確認（DevTools でキャプチャが必要）

- [x] POST `/api/scraps` と POST `/api/comments` のレスポンスの形 → 上の 2026-10-02 追記
- [x] 作成時に topics・closed・unlisted を指定できるか → unlisted は作成時に指定できる。topics と、そのほかの設定は `PUT /scraps/{slug}` で後から送る（上の追記）
- [x] コメントを編集・削除するエンドポイント → `PUT` / `DELETE /comments/{slug}`（上の追記）
- [ ] 2026年現在、サーバー側で Origin のチェックがあるか（CSRF トークンはクライアントが送っていないことを確認済み）
- [x] `comment_captcha_enabled` が有効になる条件 → 他人のスクラップにコメントするときだけ CAPTCHA が要る（上の追記）。スクラップ側でこのフラグが立つ条件は未確認

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
