# 原稿を送る

`zs` は `uv run --project <原稿リポジトリ>/tools/scrap zenn-scrap` の略。送り方は `local.md` に書いてある。

## 0. dry-run

```
zs post <topic>
```

`x` で始まる行(問題)があれば送らない。原稿を直す。止まった理由が分からなければ [diagnose.md](diagnose.md)。

## A. 普段の Chrome から送る(relay)

Claude in Chrome 拡張で、CLI が作った JavaScript を zenn.dev のタブで実行する。
JavaScript は本文の sha256 をページ側で照合し、一致したときだけ送る。本文を手で打ち直すと一致しなくなるので、**ファイルの中身をそのまま渡す**。

1. 次の手の JavaScript を作る。一時フォルダは、セッションの scratchpad(なければ `$env:TEMP\zenn-scrap`)。**原稿リポジトリの中には置かない**(コミットに混ざる)

   ```
   zs relay <topic> --count 4 --out <一時フォルダ>/step.js
   ```

   作成前なら「作成 → 設定 → 最初のコメント」の1手、作成後ならコメントを最大4件まとめた1手になる。4件で約20秒かかる。

2. `step.js` を Read で読み、その中身をそのまま実行する
   - `tabs_context_mcp`(`createIfEmpty: true`)でタブを得る
   - `navigate` で `https://zenn.dev/` を開く。**毎回開き直す**(同じページで2回実行すると、`const` の宣言がぶつかる)
   - `javascript_tool` で `step.js` の中身を実行する

3. 返った JSON を一時ファイルに書き、書き戻す

   ```
   zs record <topic> @<一時フォルダ>/result.json
   ```

   返った JSON はそのまま書く。sha256 は先頭12桁(`sha_prefix`)で照合するので、表示で全桁が伏せられても困らない。
   JSON に `error` があっても、**先に `record` する**(止まる前に送れた分を記録するため)。そのあと続きを送らずに [diagnose.md](diagnose.md) を読む。

4. `zs relay` が「送るものはない」と言うまで 1〜3 を繰り返す

5. 照合する

   ```
   zs verify <topic>
   ```

   全部 ok ならよい。Markdown まで照合するときは、`zs relay-verify <topic>` が出す JavaScript を同じ手順で実行する(`ng` が空ならよい)。

6. 開いたタブを `tabs_close_mcp` で閉じる

## B. 専用プロファイルから送る

```
zs login                       # 初回だけ。開いた Chrome でメール(確認コード)ログイン
zs post <topic> --execute
zs verify <topic>
```

この経路は、Chrome の起動と未ログインの判定までしか確かめていない。初めて使うときは、限定公開のスクラップで1件だけ試す。

## 送ったあと

- `meta.yml`(slug やコメントの slug が書き戻される)と、送った `NNN.md` をコミットする。原稿リポジトリにユーザーの未コミットの変更があることが多いので、**自分が触ったパスだけ**を `git add` する
- プッシュするかはユーザーに確かめる(記事・本と同じリポジトリなら、プッシュで Zenn のデプロイが走る。記事・本に変更がなければ内容は変わらない)
