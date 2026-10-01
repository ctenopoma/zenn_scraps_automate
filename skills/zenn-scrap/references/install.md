# 導入する

導入するものは3つ。ツール(zenn-scrap)、このスキル、スキルの設定(`local.md`)。
ツールとスキルの原本は https://github.com/ctenopoma/zenn_scraps_automate (`tools/scrap/` と `skills/zenn-scrap/`)。

## 1. 前提条件を確かめる

送り方で変わる。Chrome の拡張機能が要るのは relay だけ。

| 送り方 | 必要なもの |
| --- | --- |
| 共通 | Zenn のアカウント、git、uv(Python 3.12 は uv が用意する)、PyPI と zenn.dev への接続 |
| relay(普段の Chrome) | Claude in Chrome 拡張 1.0.36 以降、Anthropic のプランの直接契約(Pro / Max / Team / Enterprise)、`/login` でのサインイン、Claude Code を `--chrome` 付きで起動(または `/chrome` で既定にする)。WSL は非対応。出典: https://code.claude.com/docs/en/chrome |
| 専用プロファイル | インストール済みの Chrome か Edge。初回だけ Zenn にメール(確認コード)でログインできること(Google で作ったアカウントも、設定からメールログインに切り替えられる: https://info.zenn.dev/2024-11-07-change-to-email-login )。**ログインから投稿までは試していない**(Chrome の起動と未ログインの判定まで) |

relay を使うなら、ここで実際につながるかを見る。

- `tabs_context_mcp`(`createIfEmpty: true`)が使えるか。使えなければ、ユーザーに `/chrome` で接続してもらう
- 開いたタブで `https://zenn.dev/` に移り、`javascript_tool` で `(await fetch("/api/me")).status` が 200 か。401 なら、その Chrome で Zenn にログインしてもらう
- 確かめたらタブを閉じる

## 2. 原稿リポジトリを決める

Zenn の GitHub 連携リポジトリ(`articles/` と `books/` がある)のパスを、ユーザーに聞く。連携していない普通の git リポジトリでもよい(ツールが使うのは `scraps/` だけ)。
Zenn の連携が読むのは記事と本だけなので、`scraps/` と `tools/scrap/` を足しても記事・本のデプロイには影響しない(公式ガイドに明記はないが、`tools/` などを置いたリポジトリで連携が動いている)。

## 3. ツールを入れる

原稿リポジトリのルートで実行する(PowerShell)。すでに `tools/scrap/` があるなら、上書きする前にユーザーに確かめる(更新なら、原本との差分を見せてから)。

```powershell
git clone --depth 1 https://github.com/ctenopoma/zenn_scraps_automate.git $env:TEMP\zenn_scraps_automate
New-Item -ItemType Directory -Force tools | Out-Null
Copy-Item -Recurse $env:TEMP\zenn_scraps_automate\tools\scrap tools\scrap
cd tools\scrap; uv sync; cd ..\..
```

- `uv sync` は Playwright(約 37MB)を取る。回線が遅いと数分かかる。止まって見えたら、uv のキャッシュの一時フォルダが増えているかを見る(増えていれば待つ)
- `.venv` と `__pycache__` は、uv と同梱の `.gitignore` が除外する
- prettier を使っているリポジトリなら、`.prettierignore` に `scraps/` を足す(投稿後に整形されると照合で不一致になる)

動作確認: `uv run --project tools/scrap zenn-scrap --help` が出ればよい。

### Linux / WSL の場合(試していない)

動作を確かめたのは Windows 11 だけ。Linux と WSL では試していない。そう伝えたうえで進める。

- relay は WSL では使えない(Chrome 連携が WSL 非対応)。WSL なら専用プロファイル方式にするか、Windows 側で Claude Code を動かす
- uv がなければ https://docs.astral.sh/uv/ の手順で入れる
- 専用プロファイル方式は、Linux 側に入れた Chrome(既定)か Edge を使う。Windows 側の Chrome は使えない。入れられなければ Playwright の Chromium を使う: `uv run --project tools/scrap playwright install --with-deps chromium`(`--with-deps` は apt を使うので sudo が要る)。ブラウザの指定はコマンドの前に付ける(`zs --channel chromium login`)か、環境変数 `ZENN_SCRAP_CHANNEL=chromium` に置く
- 初回のログインでブラウザを画面に出す必要がある(WSL なら WSLg。`echo $DISPLAY` に値が出れば使える)
- Windows と同じフォルダ(`/mnt/c/...`)を使うなら、仮想環境を分ける: `export UV_PROJECT_ENVIRONMENT=$HOME/zenn-scrap-wsl/.venv`
- プロファイルは `~/.local/share/zenn-scrap/profile-<ブラウザ>` にできる
- コマンドは bash に読み替える

```bash
rm -rf /tmp/zenn_scraps_automate
git clone --depth 1 https://github.com/ctenopoma/zenn_scraps_automate.git /tmp/zenn_scraps_automate
test -e tools/scrap || { mkdir -p tools && cp -r /tmp/zenn_scraps_automate/tools/scrap tools/scrap; }
(cd tools/scrap && uv sync)
mkdir -p ~/.claude/skills
test -e ~/.claude/skills/zenn-scrap || cp -r /tmp/zenn_scraps_automate/skills/zenn-scrap ~/.claude/skills/zenn-scrap
```

すでにある場合(`test -e` で飛ばした場合)は、上書きの前にユーザーに確かめる。

## 4. スキルを入れる

スキルの原本 `skills/zenn-scrap/` を、`~/.claude/skills/zenn-scrap/` にコピーする(どのプロジェクトからでも使えるように、個人のスキルとして置く)。

```powershell
Copy-Item -Recurse $env:TEMP\zenn_scraps_automate\skills\zenn-scrap $HOME\.claude\skills\zenn-scrap
```

## 5. `local.md` を書く

`~/.claude/skills/zenn-scrap/local.md` に、次の形で書く。原本のリポジトリには入れない(人ごとに違うため)。

```markdown
- 原稿リポジトリ: C:\work_space\zenn
- 送り方: relay   # relay か profile
- 補足: (あれば。例: 書き方は原稿リポジトリの CLAUDE.md に従う)
```

Linux / WSL で専用プロファイル方式なら、たとえば次のようになる。

```markdown
- 原稿リポジトリ: /home/<ユーザー>/zenn
- 送り方: profile(ブラウザ: chromium)
```

## 6. コミット

原稿リポジトリで、`tools/scrap/` と `.prettierignore`(変えたなら)だけをコミットする。プッシュするかはユーザーに確かめる。

ツールやスキルを直すときは、原本を直してからコピーし直す。導入先で直接直すと、原本とずれる。
