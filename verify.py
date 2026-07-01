"""
verify.py — 最小疎通確認。gpt-5.4-mini + Responses API の web_search が
実URLの citation を返すかを確かめる。ここが通らなければ本体は動かない。
実行: python verify.py
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

EP = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
MODEL = os.environ["AZURE_MODEL_DEPLOYMENT"]
VER = os.environ.get("AZURE_OPENAI_API_VERSION", "preview")

tok = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default").token
body = {
    "model": MODEL,
    "input": "OpenAI の直近1週間の最も重要なニュースを1件、web_searchで裏取りして日本語で1文。出典を明示。",
    "tools": [{"type": "web_search"}],
    "tool_choice": "required",
}
r = requests.post(f"{EP}/openai/v1/responses?api-version={VER}",
                  headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                  data=json.dumps(body).encode("utf-8"), timeout=120)
print("HTTP", r.status_code)
r.raise_for_status()
d = r.json()

urls, text = [], ""
for it in d.get("output", []):
    if it.get("type") == "message":
        for c in it.get("content", []):
            if c.get("type") == "output_text":
                text += c.get("text", "")
                for a in c.get("annotations", []) or []:
                    if a.get("type") == "url_citation":
                        urls.append(a.get("url"))

print("\n本文:", text[:300])
print(f"\nurl_citation数: {len(urls)}")
for u in urls:
    print("  ", u)
if urls:
    print("\n✅ PASS: web_search が実URLの citation を返した。")
    sys.exit(0)
print("\n⚠️ citation 0件。tool_choice や権限を確認。")
sys.exit(2)
