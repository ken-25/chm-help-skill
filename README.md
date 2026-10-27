# chm-help-skill

Windows の CHM ヘルプファイル(`.chm`)を、AI エージェント向けの Markdown スキルフォルダに変換するツールです。目次(`.hhc`)と索引(`.hhk`)を保ったまま、ページを 1 ファイルずつ Markdown にします。

## 必要なもの

- Windows(CHM の展開に `hh.exe` を使います)
- Python 3.15 以上
- [uv](https://docs.astral.sh/uv/)(任意。`convert.ps1` から実行する場合)

標準ライブラリのみで動き、外部パッケージは不要です。

## 使い方

PowerShell から:

```powershell
.\convert.ps1 -Chm "C:\Program Files\Example\Help\example.chm" `
              -Out ".\skills\example-help" -Name example-help -Title "Example App"
```

Python から直接:

```powershell
python chm2md.py --chm "C:\Program Files\Example\Help\example.chm" `
                 --out .\skills\example-help --name example-help --title "Example App"
```

### オプション

| オプション | 説明 |
|---|---|
| `--chm` | 変換する CHM ファイル(必須) |
| `--out` | 出力先のスキルフォルダ(必須) |
| `--name` | スキル名。`SKILL.md` の `name` になる(必須) |
| `--title` | ソフトウェア名。`SKILL.md` の説明文に使う(必須) |
| `--with-images` | ページが参照する画像もコピーする |
| `--class-map` | CSS クラス → Markdown の対応表(JSON)。既定の対応表に上書きマージする |
| `--keep-work` | 展開した一時ファイルを残す(調査用) |

PowerShell 版では `-WithImages` / `-ClassMap` が対応します。

## 出力

```
OUT/
  SKILL.md      スキル定義。テンプレートから作る。既にあれば上書きしない
  SOURCE.md     出典(元ファイルのパス・サイズ・SHA-256・変換日など)
  index.md      目次。各ページへのリンク付き
  keywords.md   索引語(CHM に索引がある場合のみ)
  pages/...     ヘルプ 1 ページにつき 1 つの Markdown。CHM 内と同じ相対パス
```

- 再実行すると `pages/`・`index.md`・`keywords.md`・`SOURCE.md` を作り直します。手で編集した `SKILL.md` はそのまま残ります。
- `SKILL.md` の雛形は `templates/SKILL.md.tmpl` です。

## CSS クラスの対応表

見出しや手順を `<h1>` や `<ol>` ではなく、スタイル付きの `<div>` / `<span>` で書いているヘルプがあります。こうしたヘルプは、CSS クラス名と Markdown の対応表を渡すと構造を保ったまま変換できます。

```json
{
  "page_title": { "block": "# " },
  "step_no":    { "after": ". " }
}
```

- `block`: その要素を新しい段落として始め、先頭にこの文字列を付ける
- `after`: 要素の閉じタグの後ろにこの文字列を付ける

既定の対応表は `chm2md.py` の `DEFAULT_CLASS_MAP` にあります。

## テスト

```powershell
uv run python -m unittest discover -s tests
```

## 注意

- 変換結果には元のヘルプの内容がそのまま入ります。ヘルプはソフトウェア提供元の著作物なので、変換したものを公開・再配布しないでください。
- `SOURCE.md` には CHM のフルパスが入ります。ユーザー名などが含まれることがあるので、共有する前に確認してください。
- `hh.exe` はパスに空白を含む CHM をうまく展開できないため、一時フォルダにコピーしてから展開しています。

## ライセンス

[MIT License](LICENSE)
