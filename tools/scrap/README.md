# スクラップの投稿(zenn-scrap)

`scraps/<topic>/` に置いた Markdown を、Zenn のスクラップとして投稿・照合する CLI です。
記事と本は GitHub 連携と zenn-cli で扱い、このツールはスクラップだけに使います。

Zenn の Public API(Bearer 認証、仕様は https://zenn.dev/openapi.yaml)が一般ユーザーに開放されるまでの場つなぎとして、Zenn 専用のブラウザプロファイルを Playwright で開き、zenn.dev のページの中から内部 API を呼びます。
Cookie は取り出しません。セッションは専用プロファイルのフォルダに残るだけです。
Public API が開放されたら(設定画面に「APIキー」タブが出たら)、`--transport public-api` に切り替えます。

原本は公開リポジトリ https://github.com/ctenopoma/zenn_scraps_automate の `tools/scrap/` です。Zenn の GitHub 連携リポジトリには、このフォルダをコピーして使います(下の「導入」)。
調査の経緯と Zenn のルールとの照合は、同じリポジトリの `docs/research/` にあります(05 がルールとの照合)。

## 守ること

Zenn のルールとの照合(上記 05)で決めた条件です。ツールにも組み込んであります。

- **人がレビューしてから送る** 既定は dry-run です。表示された本文の一覧を確認してから `--execute` を付けます
- **人が実行を指示する** 定期実行(タスクスケジューラ、cron)や CI での無人実行はしません。環境変数 `CI` などがあると送信を拒否します
- **少量にする** 1日に送るコメント数に上限があります(既定 20)。送信の間は 5 秒あけます
- **止まったら再試行しない** 429 / 422 / 403、ログイン切れ、想定外の応答で止まります。POST は再試行しません
- **同じ本文を二度送らない** 投稿済みのファイルは `meta.yml` の sha256 で判定します。投稿後にファイルを直しても、再投稿はしません
- **上限を探らない** Zenn の投稿数の上限は非公開です。上限に当てて挙動を調べる目的の投稿はしません
- **秘密を書かない** 送信前に API キーや Cookie らしき文字列を検査し、見つかったら送りません。限定公開でも URL を知る人は読めます

## 導入(Zenn の GitHub 連携リポジトリへ)

zenn-cli の構成(`articles/`、`books/`)のリポジトリに、次のように足します。Zenn の GitHub 連携が読むのは記事と本だけなので、`scraps/` と `tools/scrap/` を置いても記事・本のデプロイには影響しません(公式ガイドに明記はありませんが、`tools/` や `experiments/` を置いたリポジトリで連携が動いています)。

```
<リポジトリ>/
  articles/  books/     既存(zenn-cli)
  scraps/<topic>/       スクラップの原稿(meta.yml と 001.md, 002.md ...)
  tools/scrap/          このフォルダをそのままコピー
```

1. 原本の `tools/scrap/` を、リポジトリの `tools/scrap/` にコピーします

   ```powershell
   git clone --depth 1 https://github.com/ctenopoma/zenn_scraps_automate.git $env:TEMP\zenn_scraps_automate
   New-Item -ItemType Directory -Force tools | Out-Null
   Copy-Item -Recurse $env:TEMP\zenn_scraps_automate\tools\scrap tools\scrap
   ```

2. 下の「準備」の `uv sync` を実行します。仮想環境(`.venv`)とキャッシュは、同梱の `.gitignore` と uv が除外するので、リポジトリの `.gitignore` は変えなくてよいです
3. prettier で Markdown を整形している場合は、`.prettierignore` に `scraps/` を足します。投稿後に整形されると、照合で「投稿後に変更された」と出ます
4. 下の「スクラップを書く」の形で `scraps/<topic>/` を作り、dry-run で確認します
5. 送ったあと、`meta.yml`(slug などが書き戻される)と原稿をコミットします

ツールを更新するときは、原本を直してからコピーし直します。導入先で直接直すと、原本とずれます。

## 準備

このフォルダで `uv sync` を実行します。ブラウザは既定でインストール済みの Google Chrome(`--channel chrome`)を使うので、Playwright のブラウザのダウンロードは不要です。
Edge を使う場合は `--channel msedge` か、環境変数 `ZENN_SCRAP_CHANNEL=msedge` を指定します。

```powershell
cd tools/scrap
uv sync
```

Windows と WSL で同じフォルダを共有している場合、WSL 側の仮想環境は `UV_PROJECT_ENVIRONMENT` で Linux 側のパスに分けます。

```bash
export UV_PROJECT_ENVIRONMENT=$HOME/zenn-scrap-wsl/.venv
uv sync
```

## ログイン(最初の1回とセッション切れのとき)

```powershell
uv run --project tools/scrap zenn-scrap login
```

Zenn 専用のプロファイルで Chrome が開くので、メールアドレス(確認コード)でログインします。
普段使いの Chrome のログイン状態は使えません(Chrome 136 以降、既定のプロファイルは自動操作できない)。そのため専用プロファイルで一度だけログインします。
Playwright が起動したブラウザでは Google ログインが弾かれることがあるため、メールログインを使います。

プロファイルの既定の場所は `%LOCALAPPDATA%\zenn-scrap\profile-<ブラウザ>`(例: `profile-chrome`)です。Cookie の暗号化がブラウザごとに違うので、ブラウザごとに分けています。リポジトリの外に置きます(中に置こうとすると止まります)。
場所は環境変数 `ZENN_SCRAP_PROFILE_DIR` で変えられます。

## スクラップを書く

```
scraps/<topic>/
  meta.yml            タイトル・トピック・公開設定。投稿後に slug などが書き戻される
  001.md, 002.md ...  コメント本文(1ファイル = 1コメント、番号順に投稿)
```

`meta.yml` の例です。`slug` から下はツールが書き戻すので、手で編集しません。

```yaml
title: "スクラップのタイトル"   # 100 文字まで
topic_names: [zenn, python]     # 5 件まで
unlisted: true                  # 限定公開。作成時にしか選べない
closed: false
can_others_post: false
# --- 以下は投稿ツールが管理(手で編集しない) ---
slug: null
comments: []
```

本文は1ファイル 20,000 文字までです。改行は LF に、末尾の空白・改行は削って送ります(sha256 もこの形で取ります)。

## 投稿する

リポジトリ直下で実行します。まず dry-run で送る内容を確認します。

```powershell
uv run --project tools/scrap zenn-scrap post <topic>
```

内容を確認したら `--execute` を付けて送ります。ブラウザが開き、1件ずつ送って `meta.yml` に書き戻します。

```powershell
uv run --project tools/scrap zenn-scrap post <topic> --execute
```

既存のスクラップに追記するときは、次の番号の `NNN.md` を足して同じコマンドを実行します。
`meta.yml` の title・topic_names・closed・can_others_post を変えた場合は、次の実行で反映します。

## 普段の Chrome から送る(relay)

普段使いの Chrome に Claude in Chrome 拡張が入っていれば、専用プロファイルでのログインなしに、普段の Chrome のログイン状態で送れます(2026-10-02 の初回投稿はこの方法)。
Claude Code が拡張機能の JavaScript 実行で送り、送る内容と状態は CLI が決めます。

1. `zenn-scrap relay <topic>` が次の1手の JavaScript を出します。作成前なら「作成 → 設定 → 最初のコメント」、作成後なら `--count N` で N 件のコメントをまとめて出せます
2. Claude Code が zenn.dev のタブ(毎回読み込み直す)でその JavaScript を実行します。JavaScript は本文の sha256 を照合し、一致したときだけ送ります。本文が LLM の出力を経由しても、1文字でも変われば送りません。失敗したらその場で止まります
3. 返った結果を `zenn-scrap record <topic> @結果.json` で書き戻します。sha256 の先頭12桁で手元のファイルと照合してから記録します
4. `zenn-scrap verify <topic>` で照合し、Markdown の照合は `zenn-scrap relay-verify <topic>` の JavaScript を同じタブで実行します

```powershell
uv run --project tools/scrap zenn-scrap relay <topic> --out step.js            # 作成前
uv run --project tools/scrap zenn-scrap relay <topic> --count 4 --out batch.js  # 作成後
uv run --project tools/scrap zenn-scrap record <topic> "@result.json"
```

上限・秘密情報の検査・無人実行の拒否は `post` と同じです。送信はユーザーの指示があるときだけ行います。

## 照合する

```powershell
uv run --project tools/scrap zenn-scrap verify <topic>             # タイトル・設定・コメントの slug と並び
uv run --project tools/scrap zenn-scrap verify <topic> --markdown  # ログインして Markdown も照合
```

## 止まったとき

| 表示 | 対応 |
| --- | --- |
| `ログインが切れている` | `zenn-scrap login` でログインし直してから、同じコマンドを実行します |
| `HTTP 429` | 投稿数かリクエスト数の上限です。日をあらためます。再試行や間隔の調整で回避しようとしません |
| `HTTP 422` / `HTTP 403` | 入力か権限の問題です。メッセージを読んで原稿を直します |
| `結果を確認できなかった` | 送信の途中で通信が切れました。zenn.dev で投稿されたかを目で確かめ、`meta.yml` を手で直してから再開します |
| `CAPTCHA を要求された` | 回避せずに止めています。自分のスクラップでは通常は出ません |

## 応答の形の記録

環境変数 `ZENN_SCRAP_TRACE` にファイルを指定すると、内部 API の応答の形(キー名と型)を JSONL で追記します。値は残しません。内部 API の仕様が変わって止まったときの調査に使います。

## テスト

```powershell
cd tools/scrap
uv run pytest
```

送信部分は偽の transport に差し替えてテストしています。実際の Zenn には送りません。
