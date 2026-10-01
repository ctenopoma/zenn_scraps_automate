# 03. ブラウザ自動化系（Playwright / ハイブリッド / LLMブラウザ操作 / 拡張機能 / CDP）

調査日: 2026-10-01。【事実】は出典で確認できたもの、【推測】は未検証の推論。

## 共通の前提: Google ログインの壁

- 【事実】Zenn のログイン方式は **Google** と **メール（確認コード）** の2つだけ（https://zenn.dev/enter ）。
  - Google ログインのアカウントも、設定からメールログインに切り替えられる（https://info.zenn.dev/2024-11-07-change-to-email-login ）。
- 【事実】Google は、自動化ツールが操作しているブラウザからのログインをブロックすることがある（https://support.google.com/accounts/answer/7675428 ）。
- 【事実】Playwright のメンテナは「ステルス（自動化ツールであることを隠すこと）は目標ではない」と回答している（https://github.com/microsoft/playwright/issues/19420 ）。
- 【事実】2026年の検証記事では、15以上の回避策がどれも数日で効かなくなった。結論は「初回だけ手動で認証し、以後はセッションを再利用する」（https://saas-diary.com/lessons/playwright-google-oauth-trap/ ）。
- 【推測】つまり、どの方式でも**人が一度ログインしたセッションを使い回す**設計になる。

## A. Playwright で画面を操作するスクリプト

**仕組み**
- 専用プロファイル（`launchPersistentContext` か `storageState`）に、人が一度だけ手動でログインしておく。
- スクリプトは Markdown を読み、画面上で「投稿 → スクラップを作成 → タイトル・本文を入力 → 公開する」を操作する。
  - 画面遷移の出典: https://zenn.dev/fujishiro/scraps/50ebd5deec6f7a
- 【事実】Chrome の既定プロファイルは自動化できない。専用ディレクトリが必要（https://playwright.dev/docs/api/class-browsertype ）。

**メリット**
- 非公式APIの仕様を知らなくてよい。画像アップロードなども画面経由でそのまま使える。
- スクリプトの実行時には LLM トークンを消費しない。

**デメリット**
- 【推測】UIの変更（文言やエディタの刷新）で壊れる。
  - 【事実】Zenn は 2025-12 に記事用の新エディタを出した（https://info.zenn.dev/2025-12-08-release-new-editor ）。
  - 【事実】note.com の同様の自動化では「2ヶ月に1回、セレクターが変わって動かなくなる」と報告されている（https://uravation.com/media/claude-code-note-auto-post/ ）。
- 【事実】headless 実行は検知されうる。手がかりは UA の `HeadlessChrome`、`navigator.webdriver` など（https://blog.castle.io/how-to-detect-headless-chrome-bots-instrumented-with-playwright/ ）。
- 1件あたり数十秒かかる。CI ではブラウザのインストールや Xvfb が必要。
- 【事実】storageState のファイルはなりすましに使えるため、リポジトリにコミットしてはいけない（https://playwright.dev/docs/auth ）。

**先行事例**
- 「Zenn Scraps を YAML + Playwright で自動投稿する」（https://zenn.dev/mediflow/articles/15-zenn-scraps-automation ）は、**現在404で本文を確認できない**。
- note.com の事例（https://github.com/k34259043-maker/github-actions-note ）: storageState を Base64 にして Secret に入れ、GitHub Actions で実行している。

## B. ハイブリッド（Playwright はセッション管理だけ、投稿は API）

**仕組み**
- 【事実】`context.request` / `page.request` は、ブラウザの Cookie を自動で付けて API を呼ぶ（https://playwright.dev/docs/api-testing ）。
- 【推測】`page.evaluate(() => fetch('/api/...', {credentials:'include'}))` のように同じオリジンから fetch すれば、Origin などのヘッダも自然に揃う。

**メリット**
- DevTools から Cookie を手でコピーする手間がない。
- セッション切れを検知したら、画面付きのブラウザを開いて再ログインを促す、という復旧の流れを作れる。
- UI 操作より速く、DOM の変更にも強い。

**デメリット**
- 非公式APIへの依存（02 と同じリスク）に加えて、ブラウザ周りの準備コストもかかる。
- 【推測】Public API（01）が使えるなら、この方式を選ぶ理由はほぼない。

## C. LLM にブラウザを操作させる（Playwright MCP / Claude in Chrome / Computer use / browser-use）

**トークン消費（公開されている数値）**

| 項目 | 数値 | 出典 |
|---|---|---|
| Playwright MCP と Playwright CLI の比較（30アクション） | MCP 約115k、CLI 約25k トークン | https://testdino.com/blog/playwright-cli （個人のベンチマーク） |
| アクセシビリティスナップショット1回 | 簡単なページで数百、重い SPA で 1万〜5万トークン | https://provar.com/blog/thought-leadership/the-114k-token-problem-why-playwright-mcp-burns-your-ai-coding-agents-control-on-salesforce/ （ベンダー） |
| バージョン差 | MCP の v0.0.30 から v0.0.32 で、同じタスクのトークン数が6倍に増えた | https://github.com/microsoft/playwright-mcp/issues/889 |
| スクリーンショット1枚 | ⌈幅/28⌉×⌈高さ/28⌉ トークン。1280×800 なら約1.3k | https://platform.claude.com/docs/en/build-with-claude/vision |
| Computer use の固定コスト | 約4.5k トークン | https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool |

- 【事実】Playwright MCP の README 自身が「コーディングエージェントには CLI + Skills のほうがトークン効率が良い」と書いている（https://github.com/microsoft/playwright-mcp ）。
- 【推測】スクラップ1件の投稿は10〜20ステップ程度で、**数万〜十数万トークン**かかる見込み。
  - スクラップが長くなるほど、スナップショットが大きくなり、追記1回あたりのコストも増える。
  - 本文を LLM が出力トークンとして打ち込むので、要約・改変・途中で切れるリスクがある。

**メリット**
- 実装なしですぐ試せる。UIの変化にもある程度は自力で対応する。
- **初回の調査（どのAPIが呼ばれているかの観察）や、壊れたときの診断**に向いている。

**デメリット**
- 高コスト、遅い（分単位）、結果が毎回同じとは限らない。
- 【推測】スクラップは既定で他人もコメントできる（`can_others_post: true`）。LLM が自分のスクラップを読んだとき、他人のコメントが**プロンプトインジェクションの入口**になりうる。
- 「ボットによる自動運用」に最も近い形になる。

## D. 普段のブラウザで動く拡張機能 / ユーザースクリプト

**仕組み**
- zenn.dev 上で `fetch('/api/...', {credentials:'include'})` を実行する。HttpOnly の Cookie はブラウザが自動で付けるため、**Cookie を一切取り出さずに済む**。

**メリット**
- 認証情報のリスクが最も小さい。
- セッションは普段どおり使っていれば維持される。
- 本物のブラウザなので、自動化として検知されない。

**デメリット**
- ブラウザが起動していることが前提。CI や無人実行はできない。
- 拡張機能の保守と、エージェントからの橋渡し（キューの監視など）を自作する必要がある。
- 先行事例は読み取り系（目次表示、文字数カウントなど）のみで、投稿まで行うものは見つからなかった。

## E. 既存の Chrome に CDP で接続する

- 【事実】Chrome 136 以降、既定のプロファイルでは `--remote-debugging-port` が無視される。Cookie 窃取対策のため（https://developer.chrome.com/blog/remote-debugging-port ）。
- 【事実】デバッグポートには認証がない。ローカルの任意のプロセスから、HttpOnly を含むすべての Cookie を取得できてしまう。
- 【推測】使うなら、Zenn 専用の `--user-data-dir` で起動したときだけ接続する。普段使いのプロファイルで開きっぱなしにはしない。

## GitHub Actions でセッションを扱う場合の注意

- 【事実】GitHub は、JSON などの塊を Secret にしないよう推奨している（マスキングが漏れることがあるため）。Base64 などで加工した値も、別途マスク対象に登録が必要（https://docs.github.com/en/actions/reference/security/secure-use ）。
- 【事実】GitHub ホストランナーは Azure の IP から接続する。【推測】自宅で発行したセッションをデータセンターの IP から使うと、異常検知に引っかかる可能性がある。
- 【推測】Public API のキーであれば、これらの問題はほぼ解消する。
