"""5板块定义 + 検索設定 + 配色/アイコン（wire-dispatch デザイン）。"""

# accent: 浅色版（竖条/高亮/信号格）  accent_dark: 深色版（pill背景配白字）  icon: 内联SVG名
SECTIONS = [
    {
        # 重点板块：先頭 + 記事数増 + 国内ソース優先
        "slug": "japan",
        "name": "日本国内",
        "accent": "#D6314B", "accent_dark": "#AA2439", "icon": "torii",
        "focus": "日本政府・省庁のAI政策/規制/補助金、経済安全保障・地政学、国産LLM開発、"
                 "セキュリティインシデント、企業のAI導入事例や資金調達・M&A。"
                 "単なる家電・PC・ガジェット等の値下げ/セール/クーポン情報は対象外。",
        "query": "生成AI 政府 政策 補助金 セキュリティ 国産LLM 経済安全保障 地政学 投資",
        "country": "japan",
        "include_domains": [
            "itmedia.co.jp", "atmarkit.itmedia.co.jp", "nikkei.com", "xtech.nikkei.com",
            "publickey1.jp", "ascii.jp", "watch.impress.co.jp", "cloud.watch.impress.co.jp",
            "japan.cnet.com", "japan.zdnet.com", "ledge.ai", "nikkeibp.co.jp",
        ],
        # include_domains指定時、Tavilyはtime_range併用だと該当ゼロ〜1件(アーカイブページのみ)に
        # 潰れる不具合があるため、この板块はtime_range無指定にする（代わりにqueryへ年月を付与）。
        "time_range": None,
        "min_items": 3, "max_items": 10,
    },
    {
        # OpenAIだけでなく主要AIモデル大手を横断（Claude / Gemini 等も対象）
        "slug": "models",
        "name": "生成AIモデル",
        "accent": "#0E8A87", "accent_dark": "#0B6B69", "icon": "chip",
        "focus": "OpenAI(GPT/Sora)・Anthropic(Claude)・Google(Gemini)・Meta等、主要な生成AIモデル/製品の最新動向。新モデル発表、能力、価格、API変更、提携、規制対応。",
        "query": "OpenAI GPT Anthropic Claude Google Gemini 新モデル 発表 生成AI",
    },
    {
        "slug": "cloud",
        "name": "クラウド",
        "accent": "#3654D6", "accent_dark": "#28409E", "icon": "cloud",
        "focus": "AWS / Azure / GCP の新サービス、価格改定、障害、戦略。特にAI関連クラウド機能。",
    },
    {
        "slug": "devtools",
        "name": "AI開発ツール",
        "accent": "#8A3FE0", "accent_dark": "#6B2EB0", "icon": "terminal",
        "focus": "Claude Code / Cursor / GitHub Copilot / LangChain 等の開発者ツール・agentフレームワークの新機能・リリース。",
    },
    {
        "slug": "global",
        "name": "欧米動向",
        "accent": "#C2871F", "accent_dark": "#96690E", "icon": "globe",
        "focus": "欧米大手のAI戦略、規制(EU AI Act等)、資金調達・M&A、研究ブレークスルー。",
    },
]

SECTION_BY_SLUG = {s["slug"]: s for s in SECTIONS}

# GoatCounter（アクセス解析。公開情報でありシークレットではない）
GOATCOUNTER = "https://shinmews.goatcounter.com/count"

# お問い合わせフォーム（FormSubmit、無登録・無料）。
# メール直書きは源码に露出するため、初回送信で有効化後、
# https://formsubmit.co でランダム別名を取得して差し替えると隠せる。
CONTACT_FORM_ACTION = "https://formsubmit.co/shintboku@gmail.com"
# 送信後の戻り先（FormSubmit _next）
SITE_URL = "https://shintbokuf.github.io/shinmews20260701/"

# 記事数のデフォルト（各section で min_items/max_items 上書き可）
# min < max にして「新展開が無ければ無理に埋めない」を実際に機能させる
# （min=max だと枠を埋めるため既出話題の焼き直しが選ばれてしまう）。
# 検索クレジット概算: 通常4板块×(1+3)=16 + 日本国内(1+10)=11 → 約27/日 ≈ 810/月（Tavily無料枠1000内）
MIN_ITEMS = 1
MAX_ITEMS = 3
