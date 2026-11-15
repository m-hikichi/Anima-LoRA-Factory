# Anima LoRA Factory for Docker

[Anima LoRA Factory](https://github.com/UNfukashigi/Anima-LoRA-Factory) を、NVIDIA GPU対応のDocker Desktopで動かすためのforkです。上流v6.0の配布ZIPを検証・展開し、Linuxコンテナ向けのパス操作とGPU設定を追加します。元プロジェクトの説明と更新履歴は[UPSTREAM_README.md](UPSTREAM_README.md)に保存しています。

## 必要な環境

- Windows 10/11
- Docker Desktop（Linuxコンテナ）
- Docker DesktopのGPU supportを利用できるNVIDIAドライバー
- NVIDIA GPU（学習にはVRAM 8GB以上を推奨）
- Anima Base Model、Anima VAE、Qwen3の各モデルファイル

モデルファイルはこのリポジトリやDockerイメージには含まれません。

## セットアップ

`.env.example`を`.env`として複製し、Windows側のフォルダーを設定します。

```dotenv
APP_PORT=8000
DATASETS_DIR=C:/AI/Anima/datasets
MODELS_DIR=C:/AI/Anima/models
OUTPUT_DIR=C:/AI/Anima/output
HF_CACHE_DIR=C:/AI/Anima/huggingface
MIXED_PRECISION=auto
```

| 用途 | コンテナ内パス | 権限 |
| --- | --- | --- |
| 学習画像・caption | `/workspace/datasets` | 読み書き |
| Base Model・VAE・Qwen3 | `/workspace/models` | 読み取り専用 |
| 学習結果 | `/workspace/output` | 読み書き |
| Hugging Face cache | `/workspace/huggingface` | 読み書き |

## 起動

RTX 20/30/40シリーズ、およびCUDA 12.8で動作するGPU:

```powershell
docker compose up --build
```

RTX 50シリーズでCUDA 13.0構成を使う場合:

```powershell
docker compose -f compose.yaml -f compose.blackwell.yaml up --build
```

起動後に <http://localhost:8000> を開きます。参照ボタンでは、Dockerへマウントしたフォルダーだけを選択できます。

停止:

```powershell
docker compose down
```

## 学習画像の取得

`tools/danbooru-dataset-downloader`に、Danbooru公式APIから学習画像とcaptionを取得するCLIを同梱しています。取得結果は`.env`の`DATASETS_DIR`へ直接保存されます。

```powershell
docker compose --profile tools run --rm dataset-downloader `
  "hatsune_miku" `
  --rating general `
  --order popular `
  --image-count 20 `
  --output /datasets/hatsune_miku
```

取得後、GUIで`/workspace/datasets/hatsune_miku`を選択します。認証、rating、並び順などは[ツールのREADME](tools/danbooru-dataset-downloader/README.md)を参照してください。

## GPUとprecision

`MIXED_PRECISION=auto`ではGPU capabilityを調べ、RTX 2060などTuring世代では`fp16`、対応する新しいGPUでは`bf16`を選択します。問題の切り分けが必要な場合だけ、`.env`で`fp16`または`bf16`を明示してください。

GPU確認:

```powershell
docker compose exec app python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## 上流更新の取り込み

`origin`はこのfork、`upstream`は元リポジトリとして設定します。作業ツリーがcleanな状態で次を実行します。

```powershell
./scripts/sync-upstream.ps1
```

スクリプトは`upstream/main`を取得して`upstream/vX.Y`更新ブランチを作り、上流変更のmerge、最新ZIPのSHA-256更新、Dockerビルド検証を行います。検証に失敗しても`main`は変更しません。更新ブランチ上で`docker/materialize.py`を上流差分に合わせて修正できます。

## セキュリティ上の制約

- Web UIは既定で`127.0.0.1`だけに公開されます。
- APIから参照できるのは設定したdatasets、models、outputマウント配下だけです。
- symlinkや`..`を使ったマウント外参照は拒否されます。
- ホストPCのシャットダウンと、実行中の依存パッケージ再インストールは無効です。

## テスト

```powershell
docker run --rm -v "${PWD}:/work" -w /work python:3.11-slim python -m unittest discover -s tests -v
docker compose config --quiet
```

実モデルを使う学習確認には、別途Anima Base Model、VAE、Qwen3とデータセットが必要です。

## License

元プロジェクトと同じApache License 2.0です。詳細は[LICENSE](LICENSE)を参照してください。
