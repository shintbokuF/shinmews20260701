import os, sys
from playwright.sync_api import sync_playwright
base = os.path.dirname(os.path.abspath(__file__))
idx = "file:///" + os.path.join(base, "output", "index.html").replace("\\", "/")
# 拿第一篇文章
import glob
art = sorted(glob.glob(os.path.join(base, "output", "articles", "*.html")))[0]
arturl = "file:///" + art.replace("\\", "/")
sd = os.path.join(base, "_shots")
os.makedirs(sd, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge")
    pg = b.new_page(viewport={"width": 1280, "height": 1600}, device_scale_factor=2)
    pg.goto(idx); pg.wait_for_timeout(600)
    pg.screenshot(path=os.path.join(sd, "index.png"), full_page=True)
    pg.goto(arturl); pg.wait_for_timeout(600)
    pg.screenshot(path=os.path.join(sd, "article.png"), full_page=True)
    b.close()
print("shots done:", sd)
