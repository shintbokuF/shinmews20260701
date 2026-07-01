"""
collector.py — 二段構成でニュースを収集。
 Phase A(発見): 板块ごと1回、web_searchを強制し、重要ニュースの見出しリストを得る。
 Phase B(執筆): 見出しごとに1回、web_searchを強制し、単一記事の構造化JSONを生成。
                references は当該コールの url_citation でのみ許可。実引用0件の記事は破棄。
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

log = logging.getLogger("collector")
_cred = DefaultAzureCredential()


def _token() -> str:
    return _cred.get_token("https://cognitiveservices.azure.com/.default").token


def _norm_url(u: str) -> str:
    try:
        p = urlsplit(u.strip())
        return urlunsplit((p.scheme.lower(), p.netloc.lower(),
                           p.path.rstrip("/"), p.query, "")).rstrip("/")
    except Exception:
        return u.strip().rstrip("/")


def _call(prompt: str, timeout: int = 180) -> dict:
    """web_search を強制した Responses API 呼び出し。"""
    body = {
        "model": MODEL,
        "input": prompt,
        "tools": [{"type": "web_search"}],
        "tool_choice": "required",
    }
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    r = requests.post(RESPONSES_URL, headers=headers,
                      data=json.dumps(body).encode("utf-8"), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _call_plain(prompt: str, timeout: int = 90) -> str:
    """web_search 無しの素の呼び出し（要約生成用）。テキストを返す。"""
    body = {"model": MODEL, "input": prompt}
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}
    r = requests.post(RESPONSES_URL, headers=headers,
                      data=json.dumps(body).encode("utf-8"), timeout=timeout)
    r.raise_for_status()
    text, _ = _text_and_urls(r.json())
    return text.strip()


def summarize_section(section: dict, articles: list[dict]) -> str:
    """板块の本日ニュース群から、当日のホットトピックを2〜3文(日本語)に要約。"""
    if not articles:
        return ""
    bullets = "\n".join(f"- {a.get('title','')}: {a.get('summary_ja','')}" for a in articles)
    prompt = (
        f"次は「{section['name']}」分野の本日のニュース一覧です:\n{bullets}\n\n"
        "これらを踏まえ、今日のこの分野の要点・流れが分かるように"
        "**2〜3文の日本語**で総括してください。個別記事の羅列ではなく、"
        "全体として何が起きているかを述べる。出力は総括本文のみ（前置き・箇条書き・記号なし）。"
    )
    try:
        return _call_plain(prompt)
    except requests.HTTPError as e:
        log.warning("[%s] summary 生成失敗: %s", section["slug"], e)
        return ""


def _text_and_urls(resp: dict) -> tuple[str, set[str]]:
    parts, allowed = [], set()
    for item in resp.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") == "output_text":
                parts.append(c.get("text", ""))
                for ann in c.get("annotations", []) or []:
                    if ann.get("type") == "url_citation" and ann.get("url"):
                        allowed.add(_norm_url(ann["url"]))
    return "\n".join(parts), allowed


def _url_meta(resp: dict) -> dict[str, dict]:
    """正規化URL -> {title, url} （annotation由来の実メタ）。"""
    meta = {}
    for item in resp.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            for ann in c.get("annotations", []) or []:
                if ann.get("type") == "url_citation" and ann.get("url"):
                    meta[_norm_url(ann["url"])] = {"title": ann.get("title", ""),
                                                   "url": ann["url"]}
    return meta


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_MARKER = re.compile(r"\[(\d+)\]")


def _parse_json(text: str) -> dict:
    cleaned = _FENCE.sub("", text).strip()
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s != -1 and e != -1:
        cleaned = cleaned[s:e + 1]
    return json.loads(cleaned)


# ---------------- Phase A: 発見 ----------------
def _discovery_prompt(section: dict, today: str, lo: int, hi: int) -> str:
    return f"""あなたはIT/AI/クラウド専門のニュース編集者です。
web_search を使って「{section['name']}」板块の直近ニュースを実際に検索してください。
関注点: {section['focus']}
本日は {today}。本日優先、次点で直近3日。

最も重要な {lo}〜{hi} 件を選び、**純粋なJSONのみ**で返す（説明文・コードフェンス禁止）:
{{"stories":[{{"headline":"日本語の見出し","query_hint":"この件を深掘り検索するための具体キーワード(英日可)","source":"媒体名","published_date":"YYYY-MM-DD"}}]}}"""


def discover(section: dict, today: str, lo: int, hi: int) -> tuple[list[dict], dict]:
    resp = _call(_discovery_prompt(section, today, lo, hi))
    text, _ = _text_and_urls(resp)
    try:
        stories = _parse_json(text).get("stories", [])
    except json.JSONDecodeError as e:
        log.warning("[%s] discovery パース失敗: %s", section["slug"], e)
        stories = []
    log.info("[%s] discovery: %d件", section["slug"], len(stories))
    return stories[:hi], resp


# ---------------- Phase B: 執筆 ----------------
def _write_prompt(section: dict, story: dict, today: str) -> str:
    return f"""あなたはIT/AI/クラウド専門のニュース編集者です。
次のニュースについて web_search で**実際に複数回検索して裏取り**し、
複数ソースを踏まえた**オリジナルの日本語解説**を1本書いてください。

対象見出し: {story.get('headline','')}
検索ヒント: {story.get('query_hint','')}
板块: {section['name']} / 関注点: {section['focus']}
本日: {today}

出力は必ず**2部構成**にする:

【第1部】検索結果に基づく日本語の分析(4〜6文)。
  **主要な事実・主張ごとに、その根拠となったページを必ずインラインで出典明示せよ**
  (あなたの引用機能を使う。これが後段のreferencesの唯一の根拠になる)。
  出典を明示できない主張は書かない。複数の異なるソースを引くほど良い。

【第2部】区切り行「===JSON===」のあとに、**純粋なJSONオブジェクト1個のみ**:
{{"title":"","summary_ja":"","summary_en":"","three_lines":["短い一文","短い一文","短い一文"],"body_ja":"",
"references":[{{"id":1,"title":"","url":"","source":""}}],
"published_date":"YYYY-MM-DD","category":"{section['slug']}",
"title_highlights":[],"three_lines_highlights":[]}}

厳守:
- three_lines は「3行でわかる」要点。**各行は動詞まで含む短い一文(15〜35字程度)**にする。
  単語だけ(例:「Bedrock」)は禁止。良い例:「Grok 4.3がBedrockで利用可能に」。
- references には**第1部で実際にインライン引用したURLのみ**を入れる。第1部で引用していないURLを足さない。推測でURLを作らない。
- body_ja は第1部の内容を再構成し、段落内に [1][2] 形式の角标を references 番号に対応させて入れる。
- 原文の逐語訳・大段転載は禁止。引用は極短フレーズまで、残りは自分の言葉で。
- title_highlights / three_lines_highlights は核心keyword(製品名/モデル名/重要数字)を各1〜2語。"""


def write_article(section: dict, story: dict, today: str) -> tuple[dict | None, dict]:
    resp = _call(_write_prompt(section, story, today))
    text, allowed = _text_and_urls(resp)
    meta = _url_meta(resp)
    # 第2部(===JSON=== 以降)からJSONを取り出す。annotationは第1部由来。
    json_text = text.split("===JSON===", 1)[1] if "===JSON===" in text else text
    try:
        item = _parse_json(json_text)
    except json.JSONDecodeError as e:
        log.warning("[%s] write パース失敗: %s", section["slug"], e)
        return None, resp

    # references を許可URL集合で濾過し、実メタで補正、[n]振り直し
    kept, old_to_new = [], {}
    for ref in item.get("references") or []:
        nu = _norm_url(ref.get("url", ""))
        if nu in allowed:
            new_id = len(kept) + 1
            old_to_new[ref.get("id")] = new_id
            kept.append({
                "id": new_id,
                "title": ref.get("title") or meta.get(nu, {}).get("title", ""),
                "url": ref.get("url"),
                "source": ref.get("source", ""),
            })
        else:
            log.warning("[%s] ref破棄(検索結果外): %s", section["slug"], ref.get("url"))

    # モデルがインライン引用したのにJSON referencesに載せ忘れた実URLを補完
    kept_norm = {_norm_url(r["url"]) for r in kept}
    for nu, m in meta.items():
        if nu not in kept_norm:
            kept.append({"id": len(kept) + 1, "title": m["title"],
                         "url": m["url"], "source": ""})

    if not kept:
        log.warning("[%s] 実引用0件 → 破棄: %s", section["slug"], item.get("title", "")[:40])
        return None, resp

    def _remap(m):
        new = old_to_new.get(int(m.group(1)))
        return f"[{new}]" if new else ""

    item["body_ja"] = _MARKER.sub(_remap, item.get("body_ja", ""))
    item["references"] = kept
    item["category"] = section["slug"]
    return item, resp


# ---------------- 板块オーケストレーション ----------------
def collect_section(section: dict, today: str | None = None) -> tuple[list[dict], list[dict]]:
    """戻り値: (記事list, 生レスポンスlist[archive用])。"""
    from config import MIN_ITEMS, MAX_ITEMS
    today = today or date.today().isoformat()
    raws = []
    stories, disc_raw = discover(section, today, MIN_ITEMS, MAX_ITEMS)
    raws.append({"phase": "discovery", "slug": section["slug"], "response": disc_raw})

    articles = []
    for story in stories:
        try:
            art, raw = write_article(section, story, today)
            raws.append({"phase": "write", "slug": section["slug"],
                         "headline": story.get("headline"), "response": raw})
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
