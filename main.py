"""
main.py — 編排: 全板块collect → data/保存 → HTML描画。
使い方: python main.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime, timezone

from config import SECTIONS
from collector import collect_section
import renderer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
OUTPUT_DIR = os.path.join(BASE, "output")

log = logging.getLogger("main")


def build(today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    sections_out = []
    raws_all = []

    for sec in SECTIONS:
        log.info("=== 収集開始: %s ===", sec["name"])
        try:
            articles, raws, summary = collect_section(sec, today)
        except Exception as e:  # 板块単位で失敗を隔離
            log.exception("[%s] 収集中に例外 → スキップ: %s", sec["slug"], e)
            articles, raws, summary = [], [], ""
        raws_all.extend(raws)
        for i, art in enumerate(articles):
            art["id"] = f"{sec['slug']}-{i + 1}"
        sections_out.append({
            "slug": sec["slug"], "name": sec["name"],
            "accent": sec["accent"], "accent_dark": sec.get("accent_dark", sec["accent"]),
            "icon": sec.get("icon", "chip"),
            "articles": articles, "summary": summary,
        })

    data = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections_out,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA_DIR, f"{today}.raw.json"), "w", encoding="utf-8") as f:
        json.dump(raws_all, f, ensure_ascii=False, indent=2)

    total = sum(len(s["articles"]) for s in sections_out)
    log.info("収集完了: 合計 %d 記事", total)
    return data


def render_all(data: dict) -> None:
    """最新版を output/ に、日付スナップショットを output/archive/<date>/ に描画。
    さらに過去分を一覧する archive/index.html を生成。"""
    from config import GOATCOUNTER, CONTACT_FORM_ACTION, SITE_URL
    date_str = data["date"]
    # 最新（トップ）
    renderer.render(data, OUTPUT_DIR, archive_href="archive/index.html", goatcounter=GOATCOUNTER,
                    contact_action=CONTACT_FORM_ACTION, site_url=SITE_URL)
    # 日付スナップショット
    snap_dir = os.path.join(OUTPUT_DIR, "archive", date_str)
    renderer.render(data, snap_dir, archive_href="../index.html", goatcounter=GOATCOUNTER,
                    contact_action=CONTACT_FORM_ACTION, site_url=SITE_URL)
    # アーカイブ一覧（data/*.json の日付から）
    dates = sorted(
        (f[:-5] for f in os.listdir(DATA_DIR)
         if f.endswith(".json") and not f.endswith(".raw.json")),
        reverse=True,
    )
    renderer.render_archive_index(dates, os.path.join(OUTPUT_DIR, "archive", "index.html"),
                                  goatcounter=GOATCOUNTER)


def latest_data() -> dict:
    """最新の data/*.json を読み込む（採集せず再描画する用）。"""
    files = sorted(f for f in os.listdir(DATA_DIR)
                   if f.endswith(".json") and not f.endswith(".raw.json"))
    if not files:
        raise SystemExit("data/ にJSONがありません。まず `python main.py` で採集してください。")
    with open(os.path.join(DATA_DIR, files[-1]), encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    # `python main.py render` = 採集せず、保存済みデータから再描画のみ（UI変更用・無料/即時）
    if len(sys.argv) > 1 and sys.argv[1] in ("render", "--render-only"):
        data = latest_data()
        render_all(data)
        log.info("再描画のみ完了（採集なし）: %s", os.path.join(OUTPUT_DIR, "index.html"))
        return 0
    data = build()
    render_all(data)
    log.info("描画完了: %s", os.path.join(OUTPUT_DIR, "index.html"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
