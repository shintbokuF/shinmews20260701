"""
collector.py — 二段構成でニュースを収集（検索は Tavily、生成は gpt-5.4-mini）。
 Phase A(発見): 板块ごとに Tavily で1回検索し、モデルが重要ニュースを選別。
 Phase B(執筆): 見出しごとに Tavily で1回検索し、その結果のみを根拠に記事JSONを生成。
                references のURLは Tavily が返した結果集合でのみ許可（推測URLは破棄）。実引用0件は破棄。
"""
from __future__ import annotations

import json
import os
import re
import logging
from datetime import date
from urllib.parse import urlsplit, urlunsplit

import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
MODEL = os.environ["AZURE_MODEL_DEPLOYMENT"]
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "preview")
RESPONSES_URL = f"{ENDPOINT}/openai/v1/responses?api-version={API_VERSION}"
TAVILY_KEY = os.environ.get("TAVILY_API_KEY", "")

log = logging.getLogger("collector")
_cred = DefaultAzureCredential()


def _token() -> str:
    return _cred.get_token("https://cognitiveservices.azure.com/.default").token


def _norm_url(u: str) -> str:
    try:
        p = urlsplit((u or "").strip())
        return urlunsplit((p.scheme.lower(), p.netloc.lower(),
                           p.path.rstrip("/"), p.query, "")).rstrip("/")
    except Exception:
        return (u or "").strip().rstrip("/")


# ---------------- Tavily 検索 ----------------
def tavily_search(query: str, max_results: int = 12, time_range: str = "week",
                  country: str | None = None, include_domains: list[str] | None = None,
                  timeout: int = 40) -> list[dict]:
    """Tavily で検索し [{title,url,content,score}] を返す。1リクエスト=1 credit。
    country: その国のニュースを優先（例: japan）。include_domains: 対象ドメインを限定。"""
    if not TAVILY_KEY:
        raise RuntimeError("TAVILY_API_KEY が未設定です（.env か 環境変数）。")
    body = {
        "query": query,
        "topic": "news",
        "time_range": time_range,
        "max_results": max_results,
        "search_depth": "basic",
    }
    if country:
        body["country"] = country
    if include_domains:
        body["include_domains"] = include_domains
    r = requests.post("https://api.tavily.com/search",
                      headers={"Authorization": f"Bearer {TAVILY_KEY}",
                               "Content-Type": "application/json"},
                      data=json.dumps(body).encode("utf-8"), timeout=timeout)
    r.raise_for_status()
    return r.json().get("results", [])


def _results_block(results: list[dict]) -> str:
    """検索結果を番号付きテキストに（モデルへの提示 & 許可URL台帳）。"""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.get('title','')}\n    URL: {r.get('url','')}\n"
                     f"    抜粋: {(r.get('content','') or '')[:300]}")
    return "\n".join(lines)


# ---------------- Responses API（tool無し） ----------------
def _call_plain(prompt: str, timeout: int = 120) -> str:
    body = {"model": MODEL, "input": prompt}
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    r = requests.post(RESPONSES_URL, headers=headers,
                      data=json.dumps(body).encode("utf-8"), timeout=timeout)
    r.raise_for_status()
    parts = []
    for item in r.json().get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    parts.append(c.get("text", ""))
    return "\n".join(parts).strip()


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_MARKER = re.compile(r"\[(\d+)\]")


def _parse_json(text: str) -> dict:
    cleaned = _FENCE.sub("", text).strip()
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s != -1 and e != -1:
        cleaned = cleaned[s:e + 1]
    return json.loads(cleaned)


# ---------------- Phase A: 発見 ----------------
def _discovery_prompt(section: dict, results: list[dict], today: str, lo: int, hi: int) -> str:
    return f"""あなたはIT/AI/クラウド専門のニュース編集者です。
本日は {today}。次は「{section['name']}」分野の検索結果です:
{_results_block(results)}

この中から、本日〜直近で最も重要なニュースを {lo}〜{hi} 件選んでください。
重複する話題はまとめ、この分野({section['focus']})に本当に関連するものだけ。
純粋なJSONのみ（説明文・コードフェンス禁止）:
{{"stories":[{{"headline":"日本語の見出し","query_hint":"この件を深掘り検索する具体キーワード(英日可)"}}]}}"""


def discover(section: dict, today: str, lo: int, hi: int) -> tuple[list[dict], dict]:
    query = section.get("query") or f"{section['name']} {section['focus']}"
    results = tavily_search(query, max_results=20, country=section.get("country"),
                            include_domains=section.get("include_domains"))
    raw = {"phase": "discovery", "slug": section["slug"],
           "query": query, "results": results}
    try:
        stories = _parse_json(_call_plain(_discovery_prompt(section, results, today, lo, hi))).get("stories", [])
    except json.JSONDecodeError as e:
        log.warning("[%s] discovery パース失敗: %s", section["slug"], e)
        stories = []
    log.info("[%s] discovery: %d件", section["slug"], len(stories))
    return stories[:hi], raw


# ---------------- Phase B: 執筆 ----------------
def _write_prompt(section: dict, story: dict, results: list[dict], today: str) -> str:
    return f"""あなたはIT/AI/クラウド専門のニュース編集者です。本日は {today}。
次のニュースについて、下の検索結果**のみ**を根拠に、複数ソースを踏まえた
**オリジナルの日本語解説記事**を1本書いてください。

対象見出し: {story.get('headline','')}
板块: {section['name']} / 関注点: {section['focus']}

検索結果（この中のURLだけをreferencesに使う。これ以外のURLを書かない）:
{_results_block(results)}

制約:
- 原文の逐語訳・大段転載は禁止。各ソースからの引用は極短フレーズまで、残りは自分の言葉で。
- body_ja の段落内に [1][2] 形式の角标を入れ references 番号に対応させる。裏付けは検索結果の抜粋に基づく主張にのみ付ける。
- references の url は**上の検索結果に実在するURLのみ**。推測でURLを作らない。
- three_lines は「3行でわかる」要点。各行は動詞まで含む短い一文(15〜35字程度)。単語だけは禁止。
- title_highlights / three_lines_highlights は核心keyword(製品名/モデル名/重要数字)を各1〜2語。

純粋なJSONオブジェクト1個のみ（説明文・コードフェンス禁止）:
{{"title":"","summary_ja":"","summary_en":"","three_lines":["短い一文","短い一文","短い一文"],"body_ja":"",
"references":[{{"id":1,"title":"","url":"","source":""}}],
"published_date":"YYYY-MM-DD","category":"{section['slug']}",
"title_highlights":[],"three_lines_highlights":[]}}"""


def write_article(section: dict, story: dict, today: str) -> tuple[dict | None, dict]:
    results = tavily_search(story.get("query_hint") or story.get("headline", ""),
                            max_results=8, country=section.get("country"),
                            include_domains=section.get("include_domains"))
    raw = {"phase": "write", "slug": section["slug"],
           "headline": story.get("headline"), "results": results}
    # 許可URL台帳（正規化URL -> 実メタ）
    allowed = {_norm_url(r["url"]): {"title": r.get("title", ""), "url": r["url"]}
               for r in results if r.get("url")}
    try:
        item = _parse_json(_call_plain(_write_prompt(section, story, results, today)))
    except json.JSONDecodeError as e:
        log.warning("[%s] write パース失敗: %s", section["slug"], e)
        return None, raw

    kept, old_to_new = [], {}
    for ref in item.get("references") or []:
        nu = _norm_url(ref.get("url", ""))
        if nu in allowed:
            new_id = len(kept) + 1
            old_to_new[ref.get("id")] = new_id
            kept.append({"id": new_id,
                         "title": ref.get("title") or allowed[nu]["title"],
                         "url": allowed[nu]["url"], "source": ref.get("source", "")})
        else:
            log.warning("[%s] ref破棄(検索結果外): %s", section["slug"], ref.get("url"))

    if not kept:
        log.warning("[%s] 実引用0件 → 破棄: %s", section["slug"], item.get("title", "")[:40])
        return None, raw

    def _remap(m):
        new = old_to_new.get(int(m.group(1)))
        return f"[{new}]" if new else ""

    item["body_ja"] = _MARKER.sub(_remap, item.get("body_ja", ""))
    item["references"] = kept
    item["category"] = section["slug"]
    return item, raw


def summarize_section(section: dict, articles: list[dict]) -> str:
    """板块の本日ニュース群から当日のホットトピックを2〜3文(日本語)に要約。検索なし。"""
    if not articles:
        return ""
    bullets = "\n".join(f"- {a.get('title','')}: {a.get('summary_ja','')}" for a in articles)
    prompt = (
        f"次は「{section['name']}」分野の本日のニュース一覧です:\n{bullets}\n\n"
        "これらを踏まえ、今日のこの分野の要点・流れが分かるように**2〜3文の日本語**で"
        "総括してください。個別記事の羅列ではなく全体像を。出力は総括本文のみ。"
    )
    try:
        return _call_plain(prompt)
    except requests.HTTPError as e:
        log.warning("[%s] summary 生成失敗: %s", section["slug"], e)
        return ""


# ---------------- 板块オーケストレーション ----------------
def collect_section(section: dict, today: str | None = None) -> tuple[list[dict], list[dict], str]:
    from config import MIN_ITEMS, MAX_ITEMS
    today = today or date.today().isoformat()
    lo = section.get("min_items", MIN_ITEMS)
    hi = section.get("max_items", MAX_ITEMS)
    raws = []
    stories, disc_raw = discover(section, today, lo, hi)
    raws.append(disc_raw)

    articles = []
    for story in stories:
        try:
            art, raw = write_article(section, story, today)
            raws.append(raw)
            if art:
                articles.append(art)
        except requests.HTTPError as e:
            log.error("[%s] write HTTPエラー: %s", section["slug"], e)
    log.info("[%s] 完成: %d/%d件（引用付き）", section["slug"], len(articles), len(stories))
    summary = summarize_section(section, articles)
    return articles, raws, summary


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from config import SECTION_BY_SLUG, SECTIONS
    slug = sys.argv[1] if len(sys.argv) > 1 else "openai"
    sec = SECTION_BY_SLUG.get(slug, SECTIONS[0])
    arts, _, summary = collect_section(sec)
    print(f"\n===== {sec['name']} : {len(arts)}件 =====")
    print("要約:", summary, "\n")
    print(json.dumps(arts, ensure_ascii=False, indent=2))
