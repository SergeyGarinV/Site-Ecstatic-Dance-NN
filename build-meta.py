#!/usr/bin/env python3
"""
build-meta.py
Читает event.json и обновляет Open Graph / Twitter / JSON-LD
мета-теги в index.html. Запускать перед каждой выкладкой сайта.

Обновляет:
  • og:description, twitter:description
  • event:start_time, event:end_time
  • JSON-LD Event: startDate, endDate, offers.price, offers.url

Если в event.json дата не задана (start/date/time = null),
даты в SEO обнуляются (content=""), чтобы не висело устаревшее событие.
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


# ---------- утилиты для дат ----------

def parse_iso(value):
    if not value:
        return None
    try:
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
    """ISO в московском времени. None → None."""
    if not date:
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=MSK)
    return date.astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00")


# ---------- чтение ----------

def read_event(path):
    if not path.exists():
        print(f"[!] Не найден {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------- замена в HTML ----------

def replace_meta(html, prop, value):
    """
    Заменяет content у <meta property="prop" content="...">
    или <meta name="prop" content="...">.
    value=None  → не трогает.
    value=""    → ставит пустую строку.
    """
    if value is None:
        return html
    pattern = re.compile(
        r'(<(?:meta)\s+(?:property|name)="' + re.escape(prop) + r'"'
        r'\s+content=")([^"]*)(")',
        re.IGNORECASE,
    )
    new_html, n = pattern.subn(
        lambda m: m.group(1) + value + m.group(3), html
    )
    if n == 0:
        print(f"[i] Тег {prop} не найден — пропускаю")
    return new_html


def replace_jsonld_field(html, field, value):
    """Заменяет значение строкового поля в JSON-LD.
    value=None → не трогает. value="" → ставит пустую строку."""
    if value is None:
        return html
    pattern = re.compile(
        r'("' + re.escape(field) + r'"\s*:\s*")([^"]*)(")'
    )
    return pattern.sub(
        lambda m: m.group(1) + value + m.group(3),
        html,
        count=1,
    )


def replace_jsonld_offer_price(html, price):
    """Заменяет цену в JSON-LD (offers.price)."""
    if price is None:
        return html
    pattern = re.compile(r'("price"\s*:\s*")([^"]*)(")')
    return pattern.sub(
        lambda m: m.group(1) + str(price) + m.group(3),
        html,
        count=1,
    )


def replace_jsonld_offer_url(html, url):
    """
    Заменяет url ТОЛЬКО в блоке offers (тот, что перед price).
    organizer.url и publisher.url не трогает.
    """
    if not url:
        return html
    pattern = re.compile(
        r'("url"\s*:\s*")([^"]*)("\s*,\s*"price"\s*:)'
    )
    return pattern.sub(
        lambda m: m.group(1) + url + m.group(3),
        html,
        count=1,
    )


# ---------- проверки расхождений ----------

def check_jsonld_price(html, event):
    """Предупреждает, если offers.price в JSON-LD не совпадает с event.json."""
    m = re.search(r'"price"\s*:\s*"([^"]*)"', html)
    jsonld_price = m.group(1) if m else None
    event_price = event.get("pricing", {}).get("currentPrice")
    if jsonld_price and event_price and str(event_price) != jsonld_price:
        print(
            f"[!] Расхождение цены в JSON-LD: "
            f"в HTML={jsonld_price}, в event.json={event_price} "
            f"(после запуска станет {event_price})",
            file=sys.stderr,
        )


def check_visible_price(html, event):
    """Предупреждает, если видимая цена в hero не совпадает с event.json."""
    event_price = event.get("pricing", {}).get("currentPrice")
    if not event_price:
        return
    m = re.search(r'id="price-current"[^>]*>([^<]+)<', html)
    if not m:
        return
    visible = m.group(1).strip()
    visible_digits = re.sub(r'[^\d]', '', visible)
    if visible_digits and visible_digits != str(event_price):
        print(
            f"[!] Видимая цена #price-current = «{visible}» "
            f"не совпадает с event.json ({event_price})",
            file=sys.stderr,
        )


# ---------- основная логика ----------

def main():
    event = read_event(EVENT_FILE)

    # --- определяем дату ---
    start_dt = parse_iso(event.get("start"))
    end_dt = parse_iso(event.get("end"))

    # если start нет, пробуем собрать из date + time
    if not start_dt and event.get("date") and event.get("time"):
        try:
            parts = event["date"].split()
            day = int(parts[0])
            month_name = parts[1].lower()
            year = int(parts[2])
            month = MONTHS_NOM.index(month_name) + 1
            hh, mm = map(int, event["time"].split(":"))
            start_dt = datetime(year, month, day, hh, mm, tzinfo=MSK)
        except (ValueError, IndexError):
            print(
                "[!] Не удалось собрать дату из date + time",
                file=sys.stderr,
            )

    date_known = bool(start_dt)

    # --- ISO для SEO (пустая строка, если даты нет) ---
    start_iso = to_msk_iso(start_dt) or ""
    end_iso = to_msk_iso(end_dt) or ""

    # --- описания ---
    base = "Свободный танец без хореографии и оценок."
    date_label = format_ru(start_dt)
    time_label = format_time(start_dt)
    venue = event.get("venue", "")

    if date_known:
        og_desc = f"{base} {date_label}"
        if time_label:
            og_desc += f", {time_label}"
        if venue:
            og_desc += f". {venue}."

        tw_desc = f"{base} {date_label}"
        if time_label:
            tw_desc += f", {time_label}."
    else:
        og_desc = base
        tw_desc = base

    # --- читаем HTML ---
    if not HTML_FILE.exists():
        print(f"[!] Не найден {HTML_FILE}", file=sys.stderr)
        sys.exit(1)
    html = HTML_FILE.read_text(encoding="utf-8")

    # --- проверки ДО правок ---
    check_jsonld_price(html, event)
    check_visible_price(html, event)

    # --- заменяем ---
    html = replace_meta(html, "og:description", og_desc)
    html = replace_meta(html, "twitter:description", tw_desc)
    html = replace_meta(html, "event:start_time", start_iso)
    html = replace_meta(html, "event:end_time", end_iso)

    html = replace_jsonld_field(html, "startDate", start_iso)
    html = replace_jsonld_field(html, "endDate", end_iso)

    pricing = event.get("pricing", {})
    html = replace_jsonld_offer_price(html, pricing.get("currentPrice"))
    html = replace_jsonld_offer_url(html, event.get("ticket_url"))

    # --- записываем ---
    HTML_FILE.write_text(html, encoding="utf-8")

    # --- отчёт ---
    print("[✓] index.html обновлён:")
    print(f"    og:description       = {og_desc}")
    print(f"    twitter:description  = {tw_desc}")
    print(f"    event:start_time     = {start_iso or '(пусто — дата не задана)'}")
    print(f"    event:end_time       = {end_iso or '(пусто — дата не задана)'}")
    print(f"    JSON-LD startDate    = {start_iso or '(пусто — дата не задана)'}")
    print(f"    JSON-LD endDate      = {end_iso or '(пусто — дата не задана)'}")
    print(f"    JSON-LD offers.price = {pricing.get('currentPrice', '—')}")
    print(f"    JSON-LD offers.url   = {event.get('ticket_url', '—')}")

    if not date_known:
        print()
        print("[i] Дата события не задана в event.json.")
        print("    Даты в SEO обнулены, чтобы Google не показывал устаревшее событие.")


if __name__ == "__main__":
    main()