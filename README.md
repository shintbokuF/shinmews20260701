# AI・クラウド ニュースダイジェスト

毎日 IT/AI/クラウドの最新ニュースを収集し、NotebookLM 風のカード型静的サイトを生成する Python プロジェクト。
各カード = 1ニュース（大見出し + 日英要約 + 「3行でわかる」）。詳細ページは**複数ソースを基にAIが書いたオリジナル日本語解説**で、本文に `[1][2]` 形式の角标、末尾に出典リンク一覧。

> 方針: **「解説・導読」を生産し、トラフィックは原文へ導く。原文の代替物は作らない。** 引用URLは検索で実際に取得したもののみ。

## 構成

```
news_digest/
├── .env               # エンドポイント / モデル / API version
├── config.py          # 5板块定義 + accent配色
├── collector.py       # 二段構成でニュース収集（下記）
├── renderer.py        # Jinja2 → HTML（<mark>ハイライト / [n]アンカー）
├── main.py            # collect → data/保存 → render
├── verify.py          # 最小疎通確認（まず最初に実行）
├── templates/         # index / article テンプレート
├── static/style.css   # NotebookLM風スタイル
├── data/              # 毎日のJSON + 生レスポンス(.raw.json)アーカイブ
├── output/            # 生成された静的サイト（index.htmlをブラウザで開く）
└── crontab.example    # 毎日9:00実行例
```

## 検索・生成の要（重要な設計判断）

Azure OpenAI **Responses API + `web_search` ツール**（gpt-5.4-mini）を使用。実測で判明した制約:

1. **`tool_choice="required"` 必須**。`auto` だとモデルが検索せず記憶からURLを捏造する。
2. **実URLは最終メッセージの `url_citation` annotation でのみ取得可能**。`web_search_call` は検索語しか返さない。
3. **annotation は「インライン引用付きの自然文」を書いた時のみ生成される**。純JSON出力だと0件になる。

→ 対策として **二段構成**:
- **Phase A（発見）**: 板块ごと1回、検索を強制し重要ニュースの見出しリストを取得。
- **Phase B（執筆）**: 見出しごとに1回、「第1部=インライン引用付き分析 / 第2部=JSON」の形式で出力。
  annotation を唯一の正とし、references を濾過。**実引用0件の記事は破棄**。

> GPT-5系は Agents SDK の `bing_grounding` ツールと非互換（Responses API 互換ツールのみ対応）。gpt-4.1 は Agents SDK 側で可。

## 使い方

```bash
pip install -r requirements.txt
az login                      # DefaultAzureCredential 用
python verify.py              # まず疎通確認（PASS を確認）
python main.py                # 全板块収集 → output/index.html 生成
```

`output/index.html` をブラウザで開く（サーバ不要）。
単板块デバッグ: `python collector.py <slug>`（slug = openai/cloud/devtools/japan/global）。

## 認証（本番/cron）

cron では az CLI トークンが切れやすいため、サービスプリンシパル推奨:
`AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` を環境変数に設定すれば
`DefaultAzureCredential` が自動的に使用する。

## Azure リソース

- モデル: `gpt-5.4-mini`（`snboku-0401-resource`, rg-snboku-4892, eastus2）
- 検索: web_search（裏で Grounding with Bing 接続 `bing-grounding-conn` を使用、按次課金）
