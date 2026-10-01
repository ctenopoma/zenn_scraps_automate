# CLAUDE.md

このリポジトリは、AI が書いた Markdown を Zenn のスクラップとして自動投稿・検証する仕組みの**調査メモと、ツールの原本**（`tools/scrap/`）を置く。
Zenn の GitHub 連携リポジトリ `C:\work_space\zenn` には、`tools/scrap/` をコピーして導入している。ツールを直すときはこのリポジトリの原本を直し、コピーし直す。
投稿するスクラップの原稿（`scraps/<topic>/`）は `C:\work_space\zenn` にある（2026-10-01 に移した）。

## 必ず守ること

- **リポジトリ（`C:\work_space\zenn`）を正とする。**
  - `scraps/<topic>/meta.yml` にメタ情報を、`NNN.md` に本文を置く（1ファイル = 1コメント、番号順に投稿）。
  - 投稿結果（slug・コメントの id や slug・sha256）は `meta.yml` に書き戻す。
- **LLM の担当は Markdown を書くところまで。**
  - 投稿・検証は、毎回同じ結果になる CLI が行う。
  - ブラウザを LLM に操作させる方式（Playwright MCP など）は、調査や診断のときだけ使う。
  - 例外として、普段の Chrome から送る `relay`（2026-10-02 にユーザーが選択）では、CLI が作った JavaScript を Claude in Chrome 拡張で実行する。JavaScript は本文の sha256 を照合してから送るので、画面のクリック操作や本文の手打ちはしない。
- **投稿経路（transport）は差し替えられる作りにする。**
  - `public-api`: 本命。2026-10 時点では一般ユーザーに API キーが発行されていない。
  - `internal-api`: Cookie を使う非公式 API。
  - `browser`: 専用プロファイルの Playwright から、同一オリジンで fetch する。2026-10 時点の場つなぎ。
- **安全装置**
  - dry-run を既定にする。
  - 1日あたりの件数上限を自前で設ける。
  - 429 / 422 が返ったら即停止する。
  - POST は再試行しない（重複投稿を防ぐため）。
  - テストは `unlisted: true` で行う。
- **秘密情報**（Cookie、API キー、storageState）はコミットしない。`.env` に置く。`.gitignore` は設定済み。
- 調査メモを更新するときは、【事実】（出典 URL を付ける）と【推測】を区別して書く。

## 参照

- 調査と方針: `docs/research/00〜05`。結論は `04-comparison.md`、Zenn のルールとの照合は `05-compliance-check.md` にある。
- 引き継ぎ状況: `docs/HANDOFF.md`。
