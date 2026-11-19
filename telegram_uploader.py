#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автопостинг видео из Google Drive в Telegram канал.
"""
import os
import sys
import csv
import json
import random
import re
import requests
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parent
STATE_DIR = BASE / "state"
STATE_CSV = STATE_DIR / "state.csv"
CONFIG_PATH = BASE / "config.json"
TMP_DIR = BASE / "tmp"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".m4v": "video/x-m4v",
}

def log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {
        "interval_minutes": 20,
        "posts_per_run": 1,
        "order": "shuffle",
        "timezone": "Europe/Moscow",
        "telegram_channel_id": "@my_channel_username",
        "default_tags": ["telegram", "shorts"],
        "add_hashtag_shorts": True,
        "strip_leading_number": False
    }

def load_state():
    rows = []
    uploaded = {}
    if STATE_CSV.exists():
        with open(STATE_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)
                uploaded[r["filename"]] = r
    return rows, uploaded

def append_state(rows, new_row):
    STATE_DIR.mkdir(exist_ok=True)
    rows.append(new_row)
    with open(STATE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "telegram_msg_id", "upload_date"])
        writer.writeheader()
        writer.writerows(rows)

HASHTAG_RE = re.compile(r"#w+", re.UNICODE)

def parse_title_and_tags(stem: str, cfg: dict):
    s = stem.strip()
    if cfg.get("strip_leading_number"):
        s = re.sub(r"^d{1,4}[s._-]+", "", s).strip()
    
    hashtags = HASHTAG_RE.findall(s)
    if hashtags:
        tags = [h[1:] for h in hashtags]
        clean_title = HASHTAG_RE.sub("", s).strip()
    else:
        clean_title = s
        tags = list(cfg.get("default_tags", ["shorts"]))
        
    if cfg.get("add_hashtag_shorts", True) and "shorts" not in [t.lower() for t in tags]:
        tags.append("shorts")
        
    tags_str = " ".join([f"#{t}" for t in tags])
    caption = f"<b>{clean_title}</b>

{tags_str}"
    return clean_title, caption

def get_drive_service():
    cid = os.environ.get("GOOGLE_CLIENT_ID", "") or os.environ.get("YT_CLIENT_ID", "")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "") or os.environ.get("YT_CLIENT_SECRET", "")
    rt = os.environ.get("GOOGLE_REFRESH_TOKEN", "") or os.environ.get("YT_REFRESH_TOKEN", "")
    if not (cid and csec and rt):
        sys.exit("Ошибка: не заданы GOOGLE_CLIENT_ID (или YT_CLIENT_ID) / SECRET / REFRESH_TOKEN в Secrets.")
    
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=rt,
        client_id=cid,
        client_secret=csec,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_drive_videos(drive, folder_id: str):
    files = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'video/' and trashed = false",
            orderBy="name",
            pageSize=100,
            fields="nextPageToken, files(id, name, mimeType)",
            pageToken=page_token
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files

def download_file(drive, file_id: str, name: str, dest_dir: Path) -> Path:
    from googleapiclient.http import MediaIoBaseDownload
    import io
    dest = dest_dir / name
    request = drive.files().get_media(fileId=file_id)
    with io.FileIO(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest

def send_telegram_video(bot_token: str, channel_id: str, video_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    with open(video_path, "rb") as f:
        files = {"video": f}
        data = {
            "chat_id": channel_id,
            "caption": caption,
            "parse_mode": "HTML"
        }
        resp = requests.post(url, data=data, files=files, timeout=120)
        return resp.json()

def main():
    cfg = load_config()
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "") or os.environ.get("YOUTUBE_DRIVE_FOLDER_ID", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "") or cfg.get("telegram_channel_id", "")

    if not (folder_id and bot_token and channel_id):
        sys.exit("Ошибка: Проверьте секреты DRIVE_FOLDER_ID, TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID.")

    rows, uploaded = load_state()
    drive = get_drive_service()
    
    log("Сканирование папки Google Drive...")
    drive_files = list_drive_videos(drive, folder_id)
    
    remaining = [
        f for f in drive_files 
        if f["name"] not in uploaded and Path(f["name"]).suffix.lower() in MIME_BY_EXT
    ]

    if cfg.get("order", "shuffle") == "shuffle":
        random.shuffle(remaining)

    log(f"Всего видео в Drive: {len(drive_files)}. Не опубликовано: {len(remaining)}")

    if not remaining:
        log("Новых видео для публикации нет.")
        return

    posts_to_publish = int(cfg.get("posts_per_run", 1))
    batch = remaining[:posts_to_publish]

    TMP_DIR.mkdir(exist_ok=True)

    for f in batch:
        name = f["name"]
        stem = Path(name).stem
        file_id = f["id"]
        
        _, caption = parse_title_and_tags(stem, cfg)
        log(f"Скачивание файла: {name}...")
        
        try:
            local_path = download_file(drive, file_id, name, TMP_DIR)
            log(f"Публикация в Telegram канал {channel_id}...")
            
            result = send_telegram_video(bot_token, channel_id, local_path, caption)
            if result.get("ok"):
                msg_id = result["result"]["message_id"]
                log(f"Успешно опубликовано! Telegram message ID: {msg_id}")
                append_state(rows, {
                    "filename": name,
                    "telegram_msg_id": str(msg_id),
                    "upload_date": datetime.now(timezone.utc).isoformat()
                })
            else:
                log(f"Ошибка Telegram API: {result}")
        except Exception as e:
            log(f"Ошибка при обработке {name}: {e}")
        finally:
            if 'local_path' in locals() and local_path.exists():
                local_path.unlink()

if __name__ == "__main__":
    main()
