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

7. （同日）ユーザーの判断で、Public API の開放を待つ間の場つなぎとして、専用プロファイルの Playwright + ページ内 fetch（03-B）を採用した。
   - 内部 API の現在の呼び方は、フロントエンドの JS から読んだ（`docs/research/02` の追記）。CSRF トークンは不要。作成時に unlisted を指定できる。`GET /comments/{slug}/markdown` で Markdown を照合できる。
   - Zenn のルールとの照合は `docs/research/05`。明示的に違反する条項はない。守る条件（人のレビュー、人の指示による実行、少量、上限を探らない など）をツールの仕様に組み込む。
   - 「日次上限に当てて観測する」作業はやめた（05 の条件7）。

8. （2026-10-02）ユーザーの指示で、普段使いの Chrome（Claude in Chrome 拡張）から送る `relay` を追加し、`scraps/zenn-scrap-automation` の 001〜012 を限定公開で投稿した。
   - スクラップ: https://zenn.dev/kswr/scraps/cf27fd4f854925 （限定公開で作成、コメント 12 件、`posting_route: web`）。同日、013 を追記し、ユーザーが画面から公開に切り替えた。
   - 照合: タイトル・限定公開・他人の書き込み不可・topics・コメントの slug と並びが一致。12 件すべてで Markdown の sha256 が一致。
   - 設定の更新で、`scrap` と `topic_names` を1回で送ると topics しか反映されないことが分かった（照合で `can_others_post` の不一致として発見）。別々に送り直して直し、ツールも修正した（`docs/research/02` の 2026-10-02 追記）。
   - 専用プロファイル（`%LOCALAPPDATA%\zenn-scrap\profile-chrome`）でのログインは済んでいない。普段の Chrome を使うので不要。

## 決まったこと

- CLI の実装言語は **Python（uv）**。依存は `pyproject.toml` に書き、`uv sync` で入れる（`uv pip` は使わない）。
- 場つなぎの投稿経路は2つ。**普段の Chrome から送る `relay`**（ユーザーが使う方。2026-10-02）と、専用プロファイルの Playwright + ページ内 fetch（transport 名 `browser`）。
- ツールの原本は、このリポジトリ（公開）の `tools/scrap/`。記事・本の GitHub 連携リポジトリ **`C:\work_space\zenn`**（非公開）には、そのコピーを導入している。直すときは原本を直してコピーし直す（2026-10-02 にユーザーが決定）。
- 投稿するスクラップの原稿は `C:\work_space\zenn` の `scraps/<topic>/` に置く。
- このリポジトリは、調査メモとツールの原本の置き場。導入手順は `tools/scrap/README.md` の「導入」と、原稿 `014.md`。
- 調査の過程そのものもスクラップとして公開する。原稿は `C:\work_space\zenn\scraps\zenn-scrap-automation/`（001〜）。

## 次の作業

1. 調査ログの続き（`014.md` 以降。014 は導入手順で、投稿するかはユーザーの指示待ち）を、ユーザーの指示があったときに `relay` で追記投稿する。
2. ~~公開に切り替えるかを決める~~ → 2026-10-02 にユーザーが画面から公開した。
3. Public API が開放されたら（設定画面に「APIキー」タブが出たら）、transport を `public-api` に切り替える。

## 参考にした一次情報

- Public API の公式仕様: https://zenn.dev/openapi.yaml（2026-10-01 取得、sha256 `d63ae0e2…73c7`）
- 発行画面のゲート: zenn.dev のフロントエンド（buildId `BRabT0L2RKdbXUX9eJb34`）の `/settings/api-keys` のチャンク
- zenn-cli の Public API クライアント: `zenn-dev/zenn-editor` リポジトリの `packages/zenn-cli/src/server/lib/zenn-public-api-client.ts`（v0.5.5-alpha.4）
- 内部 API のキャプチャ: https://zenn.dev/katzumi/scraps/a0357c5de7b3ea
- Cookie で読み取るツール: https://github.com/ackkerman/zenn-scrap-to-md
