# HADA Study Management Template

バージョン: `1.2.0`（External Import Release）

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

## Python setup and optional dependencies

基本的な検証、カレンダー、写真一覧、計画確認だけなら、追加パッケージなしで動作します。

PDFのテキスト抽出や画像情報の読み取りを使う場合は、リポジトリのルートで次を実行してください。

```text
python -m venv .venv
```

Windows PowerShellの場合:

```text
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS・Linuxの場合:

```text
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt`には、PDF抽出用の`pypdf`と画像解析用の`Pillow`が含まれています。インストールできない場合でも、コアCLIは動作します。OCRを使う場合は、Pythonパッケージとは別にTesseract本体が必要です。

外部取り込み対応版では、次のコマンドを使えます。

```text
python -m tools.study_cli import-inbox --dry-run
python -m tools.study_cli import-inbox
python -m tools.study_cli import-inbox --watch --interval 30
python -m tools.study_cli import-url --url https://example.com/page
python -m tools.study_cli import-chat --url chat-export.json
```

`--dry-run`はファイルを移動しません。外部URLやチャットの元データは自動削除されません。

Template本体には学習者の実データや写真を含めません。

## Usage examples

用途別の価値は [docs/guides/README.md](docs/guides/README.md) にまとめています。

### Games

- [Soulcalibur VI（ソウルキャリバー6）](docs/guides/soulcalibur-6.md) — 対戦、練習、リプレイ、課題、ランクを記録する旗艦例。
- [Tekken 8（鉄拳8）](docs/guides/tekken-8.md) — キャラクター対策、確定反撃、コンボ、対戦傾向を管理。
- [Dead or Alive 6（デッド オア アライブ6）](docs/guides/dead-or-alive-6.md) — ホールド、読み合い、壁際などの課題を記録。
- [Pokkén Tournament（ポッ拳）](docs/guides/pokken-tournament.md) — フェイズ、キャラクター別練習、対戦結果を管理。
- [Fortnite（フォートナイト）](docs/guides/fortnite.md) — モード、順位、撃破原因、エイム・建築を振り返る。
- [Tetris（テトリス）](docs/guides/tetris.md)、[Tetris 99（テトリス99）](docs/guides/tetris-99.md)、[Puyo Puyo Tetris（ぷよぷよテトリス）](docs/guides/puyo-puyo-tetris.md) — 操作、判断、スコアを追跡。
- [Pokémon GO（ポケモンGO）](docs/guides/pokemon-go.md) — 捕獲、レイド、イベント、PvP、長期目標を記録。

### Exams and study

- [High school entrance（高校受験）](docs/guides/high-school-entrance.md) — 最大3年間の学習、志望校、定期試験、模試、出願日程を管理。
- [University entrance（大学受験）](docs/guides/university-entrance.md) — 大学・学部・方式、共通テスト、個別試験、出願を追跡。
- [Second-class electrician（第二種電気工事士）](docs/guides/second-class-electrician.md) — 学科と技能、作業時間、欠陥、写真レビューを記録。
- [First-class electrician（第一種電気工事士）](docs/guides/first-class-electrician.md) — 学科・技能・関連資格への継続学習を管理。
- [Hazardous materials qualifications（危険物取扱者 乙4・乙5・甲種）](docs/guides/hazardous-materials.md) — 区分別の試験、法令、性質・消火の学習を整理。
- [Art practical examination（美大実技試験）](docs/guides/art-practical-exam.md) — デッサン、色彩、構成、面接、講評、作品写真を記録。

### Hobbies and life work

- [Motorcycle maintenance（バイク趣味・メンテナンス）](docs/guides/motorcycle-maintenance.md) — 走行、整備、費用、部品、車検・保険を記録。
- [Jogging（ジョギング）](docs/guides/jogging.md)、[Swimming（水泳）](docs/guides/swimming.md) — 距離、時間、ペース、タイム、疲労、目標を継続管理。
- [Pet growth and care（ペット成長・健康記録）](docs/guides/pet-growth.md) — 体重、食事、行動、通院、成長の変化を記録。
- [Cooking and recipe practice（料理・レシピ）](docs/guides/cooking.md)、[Daily meal planning（毎日の献立）](docs/guides/meal-planning.md) — レシピ、献立、実施結果、改善点を蓄積。
- [Anime diary（アニメ感想記録）](docs/guides/anime-diary.md) — 視聴日、作品情報、一言コメント、感想を保存。

### Research and creation

- [Nature walk and plant observation（散歩・草花観察）](docs/guides/nature-walk.md)、[Photo journal（写真日記）](docs/guides/photo-journal.md) — 観察や写真を日付単位で記録。
- [Summer research（夏休みの自由研究）](docs/guides/summer-research.md) — 観察・実験を先に記録し、後から研究レポートへ整理。
- [Creative idea log（創作・漫画アイデア帳）](docs/guides/creative-idea-log.md) — 漫画などの着想、人物、世界観、資料を蓄積。

### General operations

- [General Prompt Catalog（一般用途のプロンプト集）](docs/guides/prompt-catalog.md) — 日次記録、週次レビュー、計画、変更、安全確認に使う共通プロンプト。
- [Mobile photo workflow（モバイル写真運用）](docs/guides/mobile-photo-workflow.md) — 携帯写真を手動で年別フォルダへ取り込む方法。

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
