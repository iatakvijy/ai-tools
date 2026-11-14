"""Сканер выбросов Shorts: чем хит отличается от провала того же автора.

  scan.py <имя прогона> "запрос 1" "запрос 2" … [--каналы каналы.txt]

1. Поиск YouTube по запросам → каналы (плюс свои из каналы.txt, по ссылке в строке).
2. По каждому каналу — вкладка Shorts (последние 60): медиана просмотров, отношение ролика к медиане.
3. Пары: выбросы (≥ 5× медианы) и контроль (0,7–1,3×) того же канала по соседству во времени →
   длина, дата, первые секунды речи из автосубтитров.
4. прогоны/<имя>/: каналы.csv, ролики.csv, пары.csv, отчёт.md. Смысловой разбор пар — глазами, по отчёту.

Зависимости: pip install yt-dlp
"""
import csv
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

import yt_dlp

ROOT = Path(__file__).parent
ПОИСК = 50          # результатов на запрос
РОЛИКОВ = 60        # последних шортс на канал
МИН_РОЛИКОВ = 15    # меньше — медиана ничего не значит
ВЫБРОС = 5.0
КОНТРОЛЬ = (0.7, 1.3)
ПАР_НА_КАНАЛ = 2
ПАУЗА = 2.0         # между запросами к YouTube: 28.10 субтитры ловили 429
КАНАЛОВ = 999       # --каналов N: потолок на прогон
РЕЧЬ = True         # --без-речи: без субтитров (они первыми ловят 429)
ХИТ = 100_000       # «настоящий хит» для отчёта: выброс и не меньше стольких просмотров

flat = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True,
                         "playlistend": РОЛИКОВ, "ignoreerrors": True})
full = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True,
                         "ignoreerrors": True})


def найти_каналы(запросы, файл):
    каналы = {}
    for q in запросы:
        r = flat.extract_info(f"ytsearch{ПОИСК}:{q}", download=False) or {}
        for e in r.get("entries") or []:
            if e and e.get("channel_id"):
                c = каналы.setdefault(e["channel_id"], {"имя": e.get("channel"), "запрос": q, "в_поиске": 0})
                c["в_поиске"] += 1
        time.sleep(ПАУЗА)
    if файл:
        for line in Path(файл).read_text(encoding="utf-8").splitlines():
            if "channel/" in line:
                cid = line.split("channel/")[1].split("/")[0].strip()
                каналы.setdefault(cid, {"имя": None, "запрос": "список", "в_поиске": 0})["в_поиске"] = 999  # свои — всегда в прогоне
    return каналы


def шортс(cid):
    r = flat.extract_info(f"https://www.youtube.com/channel/{cid}/shorts", download=False)
    time.sleep(ПАУЗА)
    if not r:
        return None, None, []
    ролики = [e for e in r.get("entries") or [] if e and e.get("view_count") is not None]
    return r.get("channel"), r.get("channel_follower_count"), ролики


def начало_речи(info, секунд=5):
    caps = info.get("subtitles") or {}
    caps = caps if any(k.startswith("ru") for k in caps) else (info.get("automatic_captions") or {})
    lang = next((k for k in caps if k in ("ru", "ru-orig")), None) or next(iter(caps), None)
    if not lang:
        return ""
    url = next((f["url"] for f in caps[lang] if f.get("ext") == "json3"), None)
    if not url:
        return ""
    data = json.loads(urllib.request.urlopen(url, timeout=30).read())
    слова = []
    for ev in data.get("events", []):
        if ev.get("tStartMs", 0) > секунд * 1000:
            break
        слова += [s.get("utf8", "") for s in ev.get("segs") or []]
    return " ".join("".join(слова).split())


def пары(ролики, медиана):
    for i, e in enumerate(ролики):
        e["x"] = round(e["view_count"] / медиана, 2) if медиана else 0
        e["позиция"] = i  # 0 — самый свежий
    выбросы = sorted([e for e in ролики if e["x"] >= ВЫБРОС], key=lambda e: -e["x"])[:ПАР_НА_КАНАЛ]
    взяты, out = set(), []
    for v in выбросы:
        контроль = [e for e in ролики if КОНТРОЛЬ[0] <= e["x"] <= КОНТРОЛЬ[1] and e["id"] not in взяты]
        if not контроль:
            continue
        к = min(контроль, key=lambda e: abs(e["позиция"] - v["позиция"]))
        взяты.add(к["id"])
        out.append((v, к))
    return out


def подробно(e):
    info = full.extract_info(f"https://www.youtube.com/shorts/{e['id']}", download=False) or {}
    time.sleep(ПАУЗА)
    речь = ""
    if РЕЧЬ:
        try:
            речь = начало_речи(info)
        except Exception as err:  # 429 на субтитрах не должен ронять весь прогон
            речь = f"[субтитры: {err}]"
        time.sleep(ПАУЗА)
    return {"длина": info.get("duration"), "дата": info.get("upload_date"), "лайки": info.get("like_count"),
            "комментарии": info.get("comment_count"), "начало": речь}


def main():
    global КАНАЛОВ, РЕЧЬ
    args = sys.argv[1:]
    if "--без-речи" in args:
        args.remove("--без-речи")
        РЕЧЬ = False
    if "--каналов" in args:
        i = args.index("--каналов")
        КАНАЛОВ = int(args[i + 1])
        del args[i:i + 2]
    файл = None
    if "--каналы" in args:
        i = args.index("--каналы")
        файл = args[i + 1]
        del args[i:i + 2]
    имя, запросы = args[0], args[1:]
    out = ROOT / "прогоны" / имя
    out.mkdir(parents=True, exist_ok=True)

    каналы = найти_каналы(запросы, файл)
    каналы = dict(sorted(каналы.items(), key=lambda kv: -kv[1]["в_поиске"])[:КАНАЛОВ])
    print(len(каналы), "каналов", flush=True)

    строки_каналов, строки_роликов, строки_пар = [], [], []
    for n, (cid, c) in enumerate(каналы.items(), 1):
        имя_к, подп, ролики = шортс(cid)
        if len(ролики) < МИН_РОЛИКОВ:
            continue
        медиана = statistics.median(e["view_count"] for e in ролики)
        пп = пары(ролики, медиана)
        строки_каналов.append({"канал": имя_к or c["имя"], "id": cid, "подписчики": подп, "шортс": len(ролики),
                               "медиана": int(медиана), "макс_x": max(e["x"] for e in ролики),
                               "выбросов": sum(e["x"] >= ВЫБРОС for e in ролики),
                               "хитов": sum(e["x"] >= ВЫБРОС and e["view_count"] >= ХИТ for e in ролики),
                               "макс_просмотров": max(e["view_count"] for e in ролики), "запрос": c["запрос"]})
        for e in ролики:
            строки_роликов.append({"канал": имя_к, "id": e["id"], "название": e.get("title"),
                                   "просмотры": e["view_count"], "x": e["x"], "позиция": e["позиция"]})
        for v, к in пп:
            for роль, e in (("выброс", v), ("контроль", к)):
                строки_пар.append({"канал": имя_к, "подписчики": подп, "медиана": int(медиана), "роль": роль,
                                   "x": e["x"], "просмотры": e["view_count"], "название": e.get("title"),
                                   "ссылка": f"https://youtube.com/shorts/{e['id']}", **подробно(e)})
        print(f"{n}/{len(каналы)} {имя_к}: медиана {int(медиана)}, пар {len(пп)}", flush=True)

    for f, rows in (("каналы.csv", строки_каналов), ("ролики.csv", строки_роликов), ("пары.csv", строки_пар)):
        if rows:
            with open(out / f, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter=";")
                w.writeheader()
                w.writerows(rows)
    отчёт(out, запросы, строки_каналов, строки_пар)
    print(out)


def отчёт(out, запросы, каналы, пары_):
    def доля(rows):
        return f"{sum(r['выбросов'] > 0 for r in rows)}/{len(rows)}" if rows else "0/0"
    малые = [c for c in каналы if (c["подписчики"] or 0) < 10_000]
    средние = [c for c in каналы if 10_000 <= (c["подписчики"] or 0) < 100_000]
    крупные = [c for c in каналы if (c["подписчики"] or 0) >= 100_000]
    L = [f"# Прогон: {out.name}", "", "Запросы: " + "; ".join(запросы), "",
         f"Каналов с ≥ {МИН_РОЛИКОВ} шортс: {len(каналы)}. С выбросами (≥ {ВЫБРОС:g}× медианы):",
         f"- до 10 тыс. подписчиков: {доля(малые)}",
         f"- 10–100 тыс.: {доля(средние)}",
         f"- от 100 тыс.: {доля(крупные)}", "",
         f"Настоящие хиты (выброс и ≥ {ХИТ:,} просмотров) у каналов до 10 тыс. подписчиков: "
         f"{sum(c['хитов'] > 0 for c in малые)}/{len(малые)} каналов, всего {sum(c['хитов'] for c in малые)} хитов"
         f" на {sum(c['шортс'] for c in малые)} шортс; медиана маленьких — "
         f"{int(statistics.median([c['медиана'] for c in малые])) if малые else 0}.", "",
         "## Каналы", "", "| Канал | Подп. | Медиана | Макс × | Выбросов |", "|---|---|---|---|---|"]
    for c in sorted(каналы, key=lambda c: -c["макс_x"]):
        L.append(f"| {c['канал']} | {c['подписчики']} | {c['медиана']} | {c['макс_x']} | {c['выбросов']} |")
    L += ["", "## Пары: выброс против контроля того же канала", ""]
    for i in range(0, len(пары_), 2):
        v, к = пары_[i], пары_[i + 1]
        L += [f"### {v['канал']} (медиана {v['медиана']})", ""]
        for e in (v, к):
            L.append(f"- **{e['роль']} {e['x']}×** {e['просмотры']} · {e['длина']} с · {e['дата']} · "
                     f"лайки {e['лайки']}, комм. {e['комментарии']} — [{e['название']}]({e['ссылка']})")
            L.append(f"  - начало: «{e['начало']}»")
        L.append("")
    (out / "отчёт.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
