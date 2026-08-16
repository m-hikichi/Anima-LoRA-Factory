# Danbooru Dataset Downloader

Danbooruの公式`/posts.json` APIを使い、Anima LoRAの学習用画像、caption、投稿メタデータを取得するCLIです。HTMLスクレイピングは行いません。

## リポジトリルートから実行

このツールはルートの`compose.yaml`にone-shotサービスとして登録されています。`.env`の`DATASETS_DIR`配下へ、データセットごとのサブディレクトリを指定して保存します。

```powershell
docker compose --profile tools run --rm dataset-downloader `
  "hatsune_miku" `
  --rating general `
  --order popular `
  --image-count 20 `
  --output /datasets/hatsune_miku
```

保存した`hatsune_miku`フォルダーは、Anima LoRA Factoryの参照画面では`/workspace/datasets/hatsune_miku`として選択できます。

保存内容:

- 画像ファイル: 学習画像
- 同名の`.txt`: Danbooruタグをカンマ区切りにしたcaption
- 同名の`.json`: 元投稿メタデータ
- `search_summary.json`: 検索条件と並び順

## Ratingと並び順

ratingはタグまたは`--rating`で指定できます。

```powershell
docker compose --profile tools run --rm dataset-downloader `
  "1girl" "solo" `
  --rating g `
  --order favorites `
  --exclude-tags comic monochrome watermark `
  --image-count 50 `
  --output /datasets/solo
```

Rating: `g/general`、`s/sensitive`、`q/questionable`、`e/explicit`、`sfw`、`nsfw`

主な並び順:

- `newest`: 新着順
- `oldest`: 古い順
- `score`: スコア順
- `favorites`: お気に入り数順
- `popular`: 人気順
- `updated`: 更新順
- `random`: ランダム
- `none`: 並び順を追加しない

## 認証

認証が必要な場合は、Git管理されない`.env`へ設定します。

```dotenv
DANBOORU_USERNAME=your_username
DANBOORU_API_KEY=your_api_key
DANBOORU_USER_AGENT=anima-lora-factory-dataset-downloader/1.0 (your_username)
```

APIキーをコード、README、commitへ含めないでください。

## 単体ビルド

```powershell
docker build -t anima-danbooru-dataset-downloader ./tools/danbooru-dataset-downloader

docker run --rm `
  -v "C:/AI/Anima/datasets:/datasets" `
  anima-danbooru-dataset-downloader `
  "hatsune_miku" --rating g --image-count 20 --output /datasets/hatsune_miku
```

## 主なオプション

- `--image-count`: 除外後に保存先で利用可能にする画像数。既定値は20
- `--exclude-tags TAG [TAG ...]`: いずれかのタグを含む投稿を除外。繰り返し指定可能
- `-o`, `--output`: 保存先。既定値は`/datasets`
- `--skip-existing`: 既存画像を再取得しない
- `--sleep`: API・画像取得間隔
- `--page-size`: 1回のAPI取得件数
- `--include-deleted`: 削除済み投稿も検索対象に含める

`--exclude-tags`は投稿のDanbooruタグと完全一致で比較します。除外投稿や画像URLがない投稿は画像数に含めず、`--image-count`へ達するまで検索結果の次ページを取得します。`--skip-existing`で再取得しなかった既存画像は、利用可能な画像として数えます。

## 利用上の注意

Danbooruの利用規約、APIレート制限、各投稿のライセンスと権利を確認して利用してください。大量取得時は`--sleep`を長くし、学習へ使用できる権利がある画像だけを使用してください。動画ファイルは取得される場合がありますが、Anima LoRA Factoryの学習画像一覧では対象外です。
