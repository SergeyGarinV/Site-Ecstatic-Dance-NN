#!/usr/bin/env python3
"""
build-meta.py
Читает event.json и обновляет Open Graph / Twitter / JSON-LD
мета-теги в index.html. Запускать перед каждой выкладкой сайта.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------- настройки ----------
ROOT = Path(__file__).parent
EVENT_FILE = ROOT / "event.json"
HTML_FILE = ROOT / "index.html"

MONTHS_NOM = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

MSK = timezone(timedelta(hours=3))

# ---------- утилиты ----------

def parse_iso(value):
    if not value:
        return None
    try:
        # поддержка формата с 'Z' и смещением
        v = value.replace("Z", "+00:00")
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def format_ru(date):
    """24 октября 2026"""
    if not date:
        return None
    return f"{date.day} {MONTHS_NOM[date.month - 1]} {date.year}"


def format_time(date):
    """15:00"""
    if not date:
        return None
    return date.strftime("%H:%M")


def to_msk_iso(date):
    """ISO в московском времени, как в примере: 2026-10-24T15:00:00+03:00"""
    if not date:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=MSK)
    return date.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


def read_event(path):
    if not path.exists():
        print(f"[!] Не найден {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def replace_meta(html, prop, value):
    """
    Заменяет content у <meta property="prop" content="...">
    или <meta name="prop" content="...">.
    """
    if value is None:
        return html
    # ищем тег по property= или name=
    pattern = re.compile(
        r'(<(?:meta)\s+(?:property|name)="' + re.escape(prop) + r'"'
        r'\s+content=")([^"]*)(")',
        re.IGNORECASE,
    )
    new_html, n = pattern.subn(lambda m: m.group(1) + value + m.group(3), html)
    if n == 0:
        print(f"[i] Тег {prop} не найден — пропускаю")
    return new_html


def replace_jsonld_dates(html, start_iso, end_iso):
    """
    Точечно правит startDate / endDate внутри JSON-LD блока.
    Не трогает остальной JSON.
    """
    if start_iso:
        html = re.sub(
            r'("startDate"\s*:\s*")([^"]*)(")',
            lambda m: m.group(1) + start_iso + m.group(3),
            html,
        )
    if end_iso:
        html = re.sub(
            r'("endDate"\s*:\s*")([^"]*)(")',
            lambda m: m.group(1) + end_iso + m.group(3),
            html,
        )
    return html


# ---------- основная логика ----------

def main():
    event = read_event(EVENT_FILE)

    # --- определяем дату ---
    start_dt = parse_iso(event.get("start"))
    end_dt = parse_iso(event.get("end"))

    # если start нет, пробуем собрать из date + time
    if not start_dt and event.get("date") and event.get("time"):
        try:
            day_month_year = event["date"].split()
            day = int(day_month_year[0])
            month_name = day_month_year[1].lower()
            year = int(day_month_year[2])
            month = MONTHS_NOM.index(month_name) + 1
            hh, mm = map(int, event["time"].split(":"))
            start_dt = datetime(year, month, day, hh, mm, tzinfo=MSK)
        except (ValueError, IndexError):
            print("[!] Не удалось собрать дату из date + time", file=sys.stderr)

    date_label = format_ru(start_dt) or event.get("date") or "Дата и время уточняется"
    time_label = format_time(start_dt) or event.get("time") or ""
    venue = event.get("venue", "")

    # --- описания ---
    base = "Свободный танец без хореографии и оценок."

    if date_label == "Дата и время уточняется":
        og_desc = base
        tw_desc = base
    else:
        og_desc = f"{base} {date_label}"
        if time_label:
            og_desc += f", {time_label}"
        if venue:
            og_desc += f". {venue}."

        tw_desc = f"{base} {date_label}"
        if time_label:
            tw_desc += f", {time_label}."

    # --- ISO-даты для JSON-LD и event:start_time ---
    start_iso = to_msk_iso(start_dt)
    end_iso = to_msk_iso(end_dt)

    # --- читаем HTML ---
    if not HTML_FILE.exists():
        print(f"[!] Не найден {HTML_FILE}", file=sys.stderr)
        sys.exit(1)
    html = HTML_FILE.read_text(encoding="utf-8")

    # --- заменяем ---
    html = replace_meta(html, "og:description", og_desc)
    html = replace_meta(html, "twitter:description", tw_desc)
    html = replace_meta(html, "event:start_time", start_iso)
    html = replace_meta(html, "event:end_time", end_iso)
    html = replace_jsonld_dates(html, start_iso, end_iso)

    # --- записываем ---
    HTML_FILE.write_text(html, encoding="utf-8")

    print("[✓] index.html обновлён:")
    print(f"    og:description      = {og_desc}")
    print(f"    twitter:description = {tw_desc}")
    print(f"    startDate           = {start_iso}")
    print(f"    endDate             = {end_iso}")


if __name__ == "__main__":
    main()