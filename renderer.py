"""
renderer.py — 収集した記事JSONをJinja2で静的HTMLに変換。
 - title / three_lines のkeywordを <mark> でハイライト(板块accent色の15%透過底)
 - body_ja の [n] を上付きの内部アンカーに変換、末尾に references一覧
"""
from __future__ import annotations

import os
import re
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(BASE, "templates")
STATIC = os.path.join(BASE, "static")

_MARKER = re.compile(r"\[(\d+)\]")


def _highlight(text: str, keywords: list[str], accent: str) -> Markup:
    """textをHTMLエスケープし、keyword部分を<mark>で包む。長いkeyword優先で二重包み回避。"""
    safe = str(escape(text or ""))
    for kw in sorted([k for k in (keywords or []) if k.strip()], key=len, reverse=True):
        skw = str(escape(kw))
        if skw and skw in safe and "<mark" not in _find_ctx(safe, skw):
            safe = safe.replace(
                skw,
                f'<mark style="background:{accent}26">{skw}</mark>',
                1,
            )
    return Markup(safe)


def _find_ctx(hay: str, needle: str) -> str:
    i = hay.find(needle)
    return hay[max(0, i - 8):i] if i != -1 else ""


def _render_body(body_ja: str, references: list[dict], accent: str) -> Markup:
    """段落分割 + [n]を上付きアンカーに。"""
    valid_ids = {r["id"] for r in references}
    paras = [p.strip() for p in re.split(r"\n{1,}", body_ja or "") if p.strip()]
    html_paras = []
    for p in paras:
        safe = str(escape(p))

        def _sup(m):
            n = int(m.group(1))
            if n in valid_ids:
                return (f'<sup class="cite"><a id="cite-{n}" href="#ref-{n}"'
                        f' style="color:{accent}">[{n}]</a></sup>')
            return ""
        # エスケープ後の [n] は文字列のまま残るので置換
        safe = _MARKER.sub(_sup, safe)
        html_paras.append(f"<p>{safe}</p>")
    return Markup("\n".join(html_paras))


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
    )
    return env


def render(data: dict, out_dir: str, archive_href: str = "archive/index.html",
           goatcounter: str = "", contact_action: str = "", site_url: str = "") -> None:
    """data = {date, generated_at, sections:[{slug,name,accent,accent_dark,icon,summary,articles:[...]}]}。"""
    env = _env()
    index_tpl = env.get_template("index.html.j2")
    article_tpl = env.get_template("article.html.j2")

    articles_dir = os.path.join(out_dir, "articles")
    os.makedirs(articles_dir, exist_ok=True)

    # 各記事に描画用HTMLを付与
    for sec in data["sections"]:
        for art in sec["articles"]:
            art["title_html"] = _highlight(art["title"], art.get("title_highlights"), sec["accent"])
            art["three_lines_html"] = [
                _highlight(t, art.get("three_lines_highlights"), sec["accent"])
                for t in art.get("three_lines", [])
            ]
            art["body_html"] = _render_body(art.get("body_ja", ""), art.get("references", []), sec["accent"])

    # 詳情ページ
    for sec in data["sections"]:
        for art in sec["articles"]:
            html = article_tpl.render(article=art, section=sec, data=data, goatcounter=goatcounter)
            with open(os.path.join(articles_dir, f"{art['id']}.html"), "w", encoding="utf-8") as f:
                f.write(html)

    # 首页
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_tpl.render(data=data, archive_href=archive_href, goatcounter=goatcounter,
                                 contact_action=contact_action, site_url=site_url))

    _copy_static(out_dir)


def _copy_static(out_dir: str) -> None:
    out_static = os.path.join(out_dir, "static")
    os.makedirs(out_static, exist_ok=True)
    for fn in os.listdir(STATIC):
        shutil.copy2(os.path.join(STATIC, fn), os.path.join(out_static, fn))


def render_archive_index(dates: list[str], out_path: str, goatcounter: str = "") -> None:
    """過去のダイジェスト日付一覧ページ。out_path = output/archive/index.html。"""
    env = _env()
    tpl = env.get_template("archive.html.j2")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(tpl.render(dates=dates, goatcounter=goatcounter))
    _copy_static(os.path.dirname(out_path))
