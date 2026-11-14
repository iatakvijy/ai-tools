"""Скан публичных превью t.me/s каналов с вакансиями: AI, операционка, ассистенты, PM за N дней. Запуск: python tg-вакансии.py канал1,канал2 7 (OUT_DIR — куда json)."""
import re, json, sys, html, urllib.request, datetime, os

CH = sys.argv[1].split(",")
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 14
since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=DAYS)
KW = re.compile(r"bИИb|bAIb|нейросет|n8n|автоматизац|no-?code|промпт|GPT|Claude|LLM|ассистент|помощник руководителя|операционн|project.?manager|менеджер проект|координатор|product|продакт|бизнес-ассистент|customer success|аккаунт", re.I)
BAD = re.compile(r"senior|leadb|тимлид|middle+|от 3 лет|от 5 лет|3+ ?(года|лет)|5+ ?лет|продаж|холодн|звонк|курс[ыа]? |обучение за|офис в|только офис|релокац|английский C1|fluent", re.I)
out = []


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")


for ch in CH:
    before, n, kept = "", 0, 0
    for _ in range(4):
        try:
            h = get(f"https://t.me/s/{ch}{before}")
        except Exception as e:
            print(ch, "ERR", e); break
        posts = []
        for blk in h.split('tgme_widget_message_wrap')[1:]:
            pid = re.search(r'data-post="([^"]+)"', blk)
            dt = re.search(r'<time datetime="([^"]+)"', blk)
            tx = re.search(r'js-message_text[^>]*>(.*?)</div>', blk, re.S)
            if pid and dt:
                posts.append((pid.group(1), tx.group(1) if tx else "", dt.group(1)))
        if not posts:
            print(ch, "no posts"); break
        old = False
        for pid, txt, dt in posts:
            d = datetime.datetime.fromisoformat(dt)
            n += 1
            if d < since:
                old = True; continue
            t = html.unescape(re.sub(r"<br\s*/?>", "\n", txt or ""))
            t = re.sub(r"<[^>]+>", "", t)
            if KW.search(t) and not BAD.search(t[:400]):
                out.append({"ch": ch, "u": "https://t.me/" + pid, "d": dt[:10], "t": t[:1200]}); kept += 1
        if old:
            break
        first = re.findall(r'data-post="[^/]+/(\d+)"', h)
        if not first: break
        before = f"?before={min(map(int, first))}"
    print(ch, "posts", n, "kept", kept, flush=True)
json.dump(out, open(os.path.join(os.environ.get("OUT_DIR", "."), "tg_jobs_out.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("TOTAL", len(out))
