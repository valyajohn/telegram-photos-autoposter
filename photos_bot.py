#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Парсер и автопостинг чувственных и дерзких фотосессий (Unsplash API) в Telegram канал.
- С антирекламным фильтром.
- С дерзким сленгом, чувственной эстетикой и хэштегами.
"""
import os
import sys
import csv
import json
import random
import requests
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "state"
STATE_CSV = STATE_DIR / "photos_state.csv"

AD_BLACKLIST = [
    "sale", "discount", "black friday", "cyber monday", "buy", "promo", 
    "ad", "sponsored", "shop", "price", "offer", "deal", "скидка", 
    "распродажа", "акция", "купить", "реклама", "спецпредложение"
]

SLANG_INTROS = [
    "🔥 Чувственный вайб и эстетика:",
    "⚡ Дерзкие кадры на стиле:",
    "🖤 Максимальное притяжение:",
    "💎 Атмосфера страсти и стиля:",
    "🌪️ Дикий и завораживающий вайб:",
    "🎯 На грани эстетики:"
]

SLANG_OUTROS = [
    "Этот взгляд говорит обо всем. 🧊",
    "Уровень магнетизма зашкаливает. ✨",
    "Просто безупречная грация и стиль. 🖤",
    "Кадры, от которых невозможно отвести глаз. 🔥",
    "Эстетика, пробирающая до мурашек. ⚡"
]

SENSUAL_QUERIES = [
    "sensual moody portrait aesthetic fashion lingerie art",
    "provocative dark aesthetic model portrait",
    "boudoir fashion aesthetic editorial",
    "stylish sensual portrait dark vibe"
]

HASHTAG_POOL = [
    "эстетика", "вайб", "стиль", "чувственность", "модель", 
    "sensual", "aesthetic", "mood", "boudoir", "dark", "vibe"
]

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def load_state():
    uploaded = set()
    if STATE_CSV.exists():
        with open(STATE_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                uploaded.add(r["photo_id"])
    return uploaded

def save_state(photo_id: str):
    STATE_DIR.mkdir(exist_ok=True)
    file_exists = STATE_CSV.exists()
    with open(STATE_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["photo_id", "upload_date"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "photo_id": photo_id,
            "upload_date": datetime.now(timezone.utc).isoformat()
        })

def is_clean_content(text: str) -> bool:
    text_lower = text.lower()
    for word in AD_BLACKLIST:
        if word in text_lower:
            return False
    return True

def fetch_aesthetic_photos():
    client_id = os.environ.get("UNSPLASH_ACCESS_KEY", "DEMO_KEY")
    url = "https://api.unsplash.com/photos/random"
    query = random.choice(SENSUAL_QUERIES)
    params = {
        "query": query,
        "count": 1,
        "client_id": client_id
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else [data]
    except Exception as e:
        log(f"Ошибка запроса: {e}")
    return []

def send_telegram_photo(bot_token: str, channel_id: str, image_url: str, caption: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    data = {"chat_id": channel_id, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
    resp = requests.post(url, data=data, timeout=30)
    return resp.json()

def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    if not (bot_token and channel_id):
        sys.exit("Ошибка: не заданы секреты бота или канала.")

    uploaded = load_state()
    photos = fetch_aesthetic_photos()

    for p in photos:
        photo_id = p.get("id")
        if photo_id in uploaded:
            continue

        desc = p.get("description") or p.get("alt_description") or "sensual aesthetic vibe"
        if not is_clean_content(desc):
            log(f"Пропущено рекламное фото ({photo_id})")
            continue

        image_url = p["urls"]["regular"]
        author = p["user"]["name"]

        intro = random.choice(SLANG_INTROS)
        outro = random.choice(SLANG_OUTROS)
        tags = random.sample(HASHTAG_POOL, 4)
        tags_str = " ".join([f"#{t}" for t in tags])

        caption = f"{intro}\n\n<b>{desc.capitalize()}</b>\n\n{outro}\n\n📸 Photo by <i>{author}</i>\n\n{tags_str}"

        log(f"Публикация чувственной фотосессии {photo_id} в канал {channel_id}...")
        result = send_telegram_photo(bot_token, channel_id, image_url, caption)
        if result.get("ok"):
            log("Фото успешно опубликовано в канал!")
            save_state(photo_id)
            break
        else:
            log(f"Ошибка Telegram API: {result}")

if __name__ == "__main__":
    main()
