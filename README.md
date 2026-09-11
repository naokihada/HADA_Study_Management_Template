# HADA Study Management Template

高校受験、大学受験、資格・技能試験、作品制作をファイルベースで管理する
汎用テンプレートです。

v1は、学習記録、JIRA型の計画、試験・出願日程、任意の写真の日付グループ化、
軽量な検証を対象とします。Web、通知、グラフ、AI採点はv1の対象外です。

運用上の注意は [AGENTS.md](AGENTS.md)、用途別の使い方は [docs/guides/README.md](docs/guides/README.md) を参照してください。

```text
python tools/study_cli.py validate
python tools/study_cli.py calendar
python tools/study_cli.py photos
python tools/study_cli.py summary
python tools/study_cli.py domain-status
python tools/study_cli.py domain-change --to soulcalibur-6
python tools/study_cli.py ai-reset
```

Template本体には学習者の実データや写真を含めません。

## Usage examples

用途別の価値は [docs/guides/README.md](docs/guides/README.md) にまとめています。

### Main Study Targets

- [Study and exam guides](docs/guides/study-guides.md) — 高校受験、大学受験、資格、技能、美大

### Competitive Gaming

- [Soulcalibur VI improvement](docs/guides/soulcalibur-6.md) — 旗艦使用例
- [Tekken 8 improvement](docs/guides/tekken-8.md)
- [Dead or Alive 6 improvement](docs/guides/dead-or-alive-6.md)
- [Pokkén Tournament improvement](docs/guides/pokken-tournament.md)
- [Fortnite improvement](docs/guides/fortnite.md)
- [Tetris improvement](docs/guides/tetris.md)
- [Tetris 99 improvement](docs/guides/tetris-99.md)
- [Puyo Puyo Tetris improvement](docs/guides/puyo-puyo-tetris.md)
- [Pokémon GO long-term record](docs/guides/pokemon-go.md)
- [Prompt catalog](docs/guides/prompt-catalog.md) — Tekken 8、DOA6、ポッ拳、Fortnite、Tetris、Pokémon GOなど
- [High school entrance](docs/guides/high-school-entrance.md)
- [University entrance](docs/guides/university-entrance.md)
- [Second-class electrician](docs/guides/second-class-electrician.md)
- [First-class electrician](docs/guides/first-class-electrician.md)
- [Hazardous materials qualifications](docs/guides/hazardous-materials.md)
- [Art practical examination](docs/guides/art-practical-exam.md)

### Activity, Maintenance, and Research

- [Motorcycle maintenance](docs/guides/motorcycle-maintenance.md)
- [Summer research](docs/guides/summer-research.md)
- [Jogging](docs/guides/jogging.md)
- [Swimming](docs/guides/swimming.md)
- [Pet growth and care](docs/guides/pet-growth.md)
- [Creative idea log](docs/guides/creative-idea-log.md)
- [Cooking and recipe practice](docs/guides/cooking.md)
- [Daily meal planning](docs/guides/meal-planning.md)
- [Anime diary](docs/guides/anime-diary.md)
- [Nature walk and plant observation](docs/guides/nature-walk.md)
- [Photo journal](docs/guides/photo-journal.md)
- [Mobile photo workflow](docs/guides/mobile-photo-workflow.md)
- [Prompt catalog](docs/guides/prompt-catalog.md) — ジョギング、水泳、ペット、創作アイデア帳

### Continuous upgrades

- 高校受験 → 大学受験
- 危険物乙4 → 乙5・甲種
- 第2種電気工事士 → 第1種電気工事士
- 同一ゲームファミリー内の別タイトル・別モード

初期化後のドメインはロックされます。関連変更は確認付き、非互換変更は警告と履歴保存を伴う強制変更として扱います。

## Disclaimer and freedom of use

このリポジトリのテンプレート、使用例、設定例、プロンプト例は、作者が独自に作成した特定の学習法・攻略法・健康法を保証するものではありません。勉強内容、練習方法、ゲーム攻略の観点、料理や献立の例、栄養値の推定、草花の同定候補などは、ChatGPTのAIがインターネット上の情報を参照して自動的に作成・整理した例を含みます。作者の特別な思想、個別の指導経験、特定の結果を約束する意図が含まれているとは限りません。

インターネット上の情報は、古くなっていたり、地域・年度・学校・試験方式・ゲームのパッチ・個人条件によって異なったり、相互に矛盾したりする可能性があります。試験日、受験資格、法令、安全手順、ゲーム仕様、レシピの材料、健康・栄養情報、植物名などは、利用者自身が公式情報または適切な専門家へ確認してください。

このテンプレートを使った結果として、合格、成績向上、ランク向上、技能向上、健康改善、減量、栄養改善、料理の成功、費用削減、植物同定、故障発見など、いかなる結果や効果も保証しません。AIの出力は記録整理・計画作成の補助であり、教師、講師、コーチ、医師、管理栄養士、獣医師、資格者、公式試験機関などの判断を代替しません。

写真からのカロリー、タンパク質、アレルゲン、材料、健康状態、植物種、機械の状態などの推定は特に不確実です。医療、食事療法、薬、危険作業、緊急対応、安全判断には、写真やAI出力だけを使わないでください。

利用者は、ライセンスと適用法令の範囲で、このテンプレートと使用例を自由に使用、改変、拡張、組み合わせ、再構成できます。利用者自身のデータ、プライバシー、著作権、安全、AIサービスへの入力内容、最終的な判断と結果については利用者が責任を負います。詳しくは [DISCLAIMER.md](DISCLAIMER.md) を参照してください。
