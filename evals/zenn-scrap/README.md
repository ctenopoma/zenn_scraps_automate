# スキル zenn-scrap の発動の評価

`trigger-evals.json` は、スキルの説明文(description)で正しく発動するかを測る質問 20 問(発動すべき 10 問、近いが発動すべきでない 10 問)。

## 結果

| 日付 | 説明文 | 結果 |
| --- | --- | --- |
| 2026-10-02 | `skills/zenn-scrap/SKILL.md` の初版 | 20/20 合格。発動すべき質問は 3 回中 3 回、すべきでない質問は 3 回中 0 回 |

## やり直し方

[skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) の `scripts/run_eval.py` を使う(`claude -p` で 1 問ずつ流し、Skill の呼び出しを見る)。

- 実行するフォルダの上に `.claude/` がないと、`~/.claude/commands` にテスト用のファイルを書く。空のフォルダに `.claude/` を作り、そこから実行する
- Windows では、`run_eval.py` がパイプに `select.select` を使っていて動かない。読み取りをスレッドに変えたコピーで実行した
- インストール済みの `zenn-scrap` と同じ説明文が2つ並ぶので、名前に `zenn-scrap` を含むスキルが呼ばれたら「発動した」と数えた
- Python は `PYTHONUTF8=1` で動かす(Windows の既定の cp932 では SKILL.md を読めない)

```bash
cd <空のフォルダ(.claude/ あり)>
PYTHONUTF8=1 PYTHONPATH=<skill-creator のコピー> python -m scripts.run_eval \
  --eval-set <このフォルダ>/trigger-evals.json --skill-path <原本>/skills/zenn-scrap \
  --model claude-opus-5-5 --num-workers 5 --timeout 120 --runs-per-query 3 --verbose
```

最初のツール呼び出しで判定するので、別のツールを先に使ってから後でスキルを使う場合は「発動しなかった」と数える。
