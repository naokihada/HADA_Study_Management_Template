# AGENTS.md — HADA Study Management Template

このファイルは、Templateを利用・更新するAIエージェントの共通運用契約である。
公開用の目標仕様はREADMEと用途別ガイドに限定し、内部設計文書は公開しない。

## Rules

- RepositoryをSystem of Recordとする。
- `AGENTS.md` は公開物の作業規則として扱い、内部設計文書を公開しない。
- 既存変更とユーザーデータを保護する。
- 指定範囲外の変更、未依頼機能、無関係な整理を行わない。
- 実装・設定・テスト・検証結果を根拠にする。
- 不明事項は推測で確定せず、`UNKNOWN` または `REVIEW_REQUIRED` とする。
- 個人情報、成績、写真、秘密情報を公開Templateへ含めない。
- 初期化後のPrimary Domainはロックし、関連アップグレードは確認付き、非互換変更は警告付き強制変更として履歴を残す。
- `data/` と `artifacts/` はユーザーデータ、`AI/working`、`AI/cache`、`AI/reports` はリセット可能なAI作業領域として分離する。
- Template UpgradeはP/C/N三者比較とmanifestを使用する。
- Git commit、push、Release、reset、clean、force pushは自動実行しない。
- ゲーム使用例は、個別domain pack、1年運用ガイド、拡張プロンプトを同じ粒度で整備する。
- 変更後はテスト、検証、Git diff、公開安全性を確認する。

## Public boundary

このリポジトリは汎用Templateであり、個人の学習記録を保存する場所ではない。
架空データを使う利用例は別のSampleリポジトリに置く。
