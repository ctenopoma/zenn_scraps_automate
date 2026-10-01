# zenn_scraps_automate

AI が書いた Markdown を、Zenn のスクラップとして自動投稿・検証するための仕組み（作成中）。

## 方針

- このリポジトリを正（source of truth）とする。
  - 1スクラップ = 1ディレクトリ。
  - その中の1ファイル = 1コメント。
- 投稿経路は差し替えられる作りにする。本命は公式 zenn-cli の Public API（Bearer 認証）だが、2026-10 時点では一般ユーザーにキーが発行されていない。
- LLM の担当は Markdown を書くところまで。投稿と検証は、毎回同じ結果になる CLI が行う。実行時のトークン消費はほぼ0。

経緯と比較は [docs/research/](docs/research/) を参照。

## ディレクトリ構成

```
docs/research/        調査メモ（方針・規約、Public API、内部API、ブラウザ自動化、比較）
scraps/<topic>/
  meta.yml            タイトル・トピック・公開設定。投稿後に slug などが書き戻される
  001.md, 002.md ...  コメント本文（1ファイル = 1コメント、番号順に投稿）
```

## 状態

- [x] 投稿方式の調査（このブランチ: `research/posting-approaches`）
- [x] API キーの発行確認 → 404（一般ユーザーには未開放）。投稿経路は差し替え式にする
- [ ] 当面の投稿経路の決定と、限定公開でのテスト投稿
- [ ] `post` / `verify` の実装
