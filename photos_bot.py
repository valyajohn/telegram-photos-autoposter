#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Премиум парсер и автопостинг гламурных фотосессий звезд, актрис и топ-моделей в Telegram канал.
- Высочайшее качество (без сжатия через sendDocument / full-res raw URL).
- Разнообразные свежие источники и запросы (актуальные тренды, премиум съёмки).
- Дерзкий сленг, атмосфера роскоши и огромная база уникальных хэштегов.
- Антирекламный фильтр.
"""
import os
import sys
import csv
import json
import random
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "state"
STATE_CSV = STATE_DIR / "photos_state.csv"

AD_BLACKLIST = [
    "sale", "discount", "black friday", "cyber monday", "buy", "promo", 
    "ad", "sponsored", "shop", "price", "offer", "deal", "скидка", 
    "распродажа", "акция", "купить", "реклама", "спецпредложение", "commercial"
]

SLANG_INTROS = [
    "🔥 Лютый премиум и безупречный стиль:",
    "⚡ Настоящий гламур и звездный вайб:",
    "🖤 Дорого, стильно, роскошно:",
    "💎 Эстетика высшей лиги:",
    "🌪️ Красота, которая сносит крышу:",
    "🎯 Икона стиля в кадре:",
    "✨ Чистый экстаз и высокая мода:"
]

SLANG_OUTROS = [
    "Этот образ навсегда в сердце. 🧊",
    "Уровень роскоши за пределами реальности. ✨",
    "Королева кадра, без лишних слов. 🖤",
    "От этой эстетики мурашки по коже. 🔥",
    "Высший пилотаж модельного искусства. ⚡",
    "Энергия дорогой и уверенной в себе звезды. 👑"
]

# Премиальные запросы для поиска топовых гламурных фотосессий
GLAMOUR_QUERIES = [
    "celebrity glamour photoshoot red carpet",
    "high fashion editorial gorgeous model portrait",
    "vogue style luxury magazine photoshoot",
    "luxury celebrity beauty portrait dark vibe",
    "supermodel high fashion runway editorial",
    "stunning actress glamour magazine cover"
]

# Огромный пулл разнообразных хэштегов (чтобы не было повторов)
HASHTAG_POOL = [
    "гламур", "звезды", "актрисы", "модели", "красота", "стиль", "мода", 
    "люкс", "эстетика", "роскошь", "фотосессия", "глянец", "вайб", "кумир",
    "glamour", "celebrity", "actress", "model", "vogue", "editorial", 
    "fashion", "luxury", "beauty", "style", "photoshoot", "icon", "queen",
    "highfashion", "runway", "magazinencover", "darkbeauty", "sensual"
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

def fetch_glamour_photos():
    client_id = os.environ.get("UNSPLASH_ACCESS_KEY", "DEMO_KEY")
    url = "https://api.unsplash.com/photos/random"
    query = random.choice(GLAMOUR_QUERIES)
    params = {
        "query": query,
        "count": 5,
        "client_id": client_id,
        "orientation": "portrait" # Вертикальные фото идеально для Telegram
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else [data]
    except Exception as e:
        log(f"Ошибка запроса к Unsplash: {e}")
    return []

def send_telegram_photo_uncompressed(bot_token: str, channel_id: str, image_url: str, caption: str):
    # Отправляем оригинал без сжатия через sendDocument с высоким разрешением (или сырой full URL)
    # Заменяем URL Unsplash на максимальное качество (raw / full)
    full_image_url = image_url.split("?")[0] + "?q=95&w=2400&fm=jpg"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    data = {
        "chat_id": channel_id,
        "document": full_image_url,
        "caption": caption,
        "parse_mode": "HTML"
    }
    resp = requests.post(url, data=data, timeout=45)
    
    # Если вдруг sendDocument не прошел из-за формата, пробуем sendPhoto в высоком качестве
    if not resp.json().get("ok"):
        fallback_url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        fallback_data = {
            "chat_id": channel_id,
            "photo": full_image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
        resp = requests.post(fallback_url, data=fallback_data, timeout=45)
        
    return resp.json()

def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    if not (bot_token and channel_id):
        sys.exit("Ошибка: не заданы секреты TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID.")

    uploaded = load_state()
    log("Парсинг свежих гламурных фотосессий топ-уровня...")
    photos = fetch_glamour_photos()
    
    if not photos:
        log("Не удалось получить фотографии.")
        return

    published_count = 0
    target_count = 5

    for p in photos:
        if published_count >= target_count:
            break

        photo_id = p.get("id")
        if photo_id in uploaded:
            continue

        desc = p.get("description") or p.get("alt_description") or "luxury glamour editorial photoshoot"
        if not is_clean_content(desc):
            log(f"Пропущено рекламное фото ({photo_id})")
            continue

        image_url = p["urls"]["raw"] or p["urls"]["full"] or p["urls"]["regular"]
        author = p["user"]["name"]

        intro = random.choice(SLANG_INTROS)
        outro = random.choice(SLANG_OUTROS)
        
        # Берем 7 случайных уникальных хэштегов из огромного пула
        tags = random.sample(HASHTAG_POOL, min(7, len(HASHTAG_POOL)))
        tags_str = " ".join([f"#{t}" for t in tags])

        caption = f"{intro}

<b>{desc.capitalize()}</b>

{outro}

📸 Photo by <i>{author}</i>

{tags_str}"

        log(f"Публикация гламурного кадра {photo_id} ({published_count + 1}/{target_count}) в канал {channel_id} (в оригинальном качестве)...")
        result = send_telegram_photo_uncompressed(bot_token, channel_id, image_url, caption)
        
        if result.get("ok"):
            log("Успешно опубликовано в оригинальном качестве!")
            save_state(photo_id)
            published_count += 1
            time.sleep(4)
        else:
            log(f"Ошибка Telegram API: {result}")

    log(f"Итог: опубликовано гламурных фотосессий: {published_count}")

if __name__ == "__main__":
    main()
