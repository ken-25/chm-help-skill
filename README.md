# chm-help-skill

Windows の CHM ヘルプファイル(`.chm`)を、AI エージェント向けの Markdown スキルフォルダに変換するツールです。目次(`.hhc`)と索引(`.hhk`)を保ったまま、ページを 1 ファイルずつ Markdown にします。

`--format html` を付けると、ページごとに CSS と画像を埋め込んだ単独の HTML ファイル(UTF-8 BOM 付き)を作ります。単一の HTML ファイルなら取り込める他のシステムに渡すための形式です。

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
| `--chm` | 変換する CHM ファイル。`--src-dir` とどちらか一方が必須 |
| `--src-dir` | CHM ではなく、HTML のままフォルダに置かれたヘルプページを変換する |
| `--out` | 出力先のフォルダ。省略するとユーザーのダウンロードフォルダの `<CHM名またはフォルダ名>-<形式>`(例: `Base-html`) |
| `--format` | `md`(既定。Markdown スキルフォルダ)か `html`(1 ページ 1 ファイルの HTML) |
| `--name` | スキル名。`SKILL.md` の `name` になる(`md` のとき必須) |
| `--title` | ソフトウェア名。`SKILL.md` の説明文や目次の見出しに使う(必須) |
| `--with-images` | `md` のとき、ページが参照する画像もコピーする(`html` は常に埋め込む) |
| `--class-map` | `md` のとき使う CSS クラス → Markdown の対応表(JSON)。既定の対応表に上書きマージする |
| `--keep-work` | 展開した一時ファイルを残す(調査用) |

PowerShell 版では `-SrcDir` / `-Format` / `-WithImages` / `-ClassMap` が対応します。

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

### HTML 形式(`--format html`)

```
OUT/
  SOURCE.md     出典(上と同じ。HTML の合計サイズと最大のページも書く)
  index.html    目次
  keywords.html 索引語(CHM に索引がある場合のみ)
  pages/...     ヘルプ 1 ページにつき 1 つの HTML。CHM 内と同じ相対パスで、拡張子は .html
```

- 各ページは単独で開けます。CSS は `<style>` に、画像(CSS から参照される画像も含む)は `data:` URI として埋め込みます。
- 文字コードは UTF-8(BOM 付き)で、`<meta charset="utf-8">` に書き換えます。
- 本文は元のヘルプの HTML をそのまま使います。ブラウザで動かない部分は次のように扱います。
  - スクリプトはすべて外します。折りたたみ表示は、最初から開いた状態になります。
  - 用語のポップアップ(`javascript:fPopup(...)`)は、そのページへの普通のリンクにします。
  - HTML Help 専用の部品(`<object>`)と、それを押す「関連項目」のリンクは外します。
  - 同じ CHM 内へのリンク(`MS-ITS:...::/...` も含む)は、変換後のファイルへの相対リンクにします。別の CHM へのリンクは、リンクを外して文字だけ残します。
  - 見つからない画像は `[図: ファイル名]` と表示します。
- ページの先頭に、目次へのリンクと目次上の場所を 1 行足します。
- Markdown 形式とは別のフォルダに出力してください(同じフォルダには書き込みません)。

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
