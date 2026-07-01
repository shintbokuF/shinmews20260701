"""5板块定义 + 检索关注点 + 板块配色（NotebookLM 风格）。"""

# 板块 accent 色（卡片竖条 / 标签 / 高亮底色都基于此）
SECTIONS = [
    {
        "slug": "openai",
        "name": "OpenAI系",
        "accent": "#10A37F",
        "focus": "OpenAI / GPT / Codex / Sora 等モデル・製品の最新動向。新モデル発表、API変更、価格、提携、規制対応。",
    },
    {
        "slug": "cloud",
        "name": "クラウド",
        "accent": "#4285F4",
        "focus": "AWS / Azure / GCP の新サービス、価格改定、障害、戦略。特にAI関連クラウド機能。",
    },
    {
        "slug": "devtools",
        "name": "AI開発ツール",
        "accent": "#AB47BC",
        "focus": "Claude Code / Cursor / GitHub Copilot / LangChain 等の開発者ツール・agentフレームワークの新機能・リリース。",
    },
    {
        "slug": "japan",
        "name": "日本国内",
        "accent": "#EF5350",
        "focus": "日本企業のAI導入事例、国内SIer動向、政府のAI政策・規制、国産LLM。",
    },
    {
        "slug": "global",
        "name": "欧米動向",
        "accent": "#F9AB00",
        "focus": "欧米大手のAI戦略、規制(EU AI Act等)、資金調達・M&A、研究ブレークスルー。",
    },
]

SECTION_BY_SLUG = {s["slug"]: s for s in SECTIONS}

# 1板块あたりの記事数レンジ
MIN_ITEMS = 3
MAX_ITEMS = 5
