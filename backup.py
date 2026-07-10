#!/usr/bin/env python3
"""
Outline → Telegram Backup
Exports all Outline docs as markdown + media.
- Text-only archive → sent to Telegram
- Full archive (text+media) → saved locally only
"""

import os
import sys
import re
import json
import time
import tarfile
import shutil
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# ── Config ────────────────────────────────────────────────────────────
OUTLINE_URL = os.environ["OUTLINE_URL"].rstrip("/")
OUTLINE_API_KEY = os.environ["OUTLINE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID", "")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/data/backups"))
LOCAL_BACKUP_DIR = Path(os.environ.get("LOCAL_BACKUP_DIR", "/data/backups/local"))
KEEP_BACKUPS = int(os.environ.get("KEEP_BACKUPS", "4"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("outline-backup")

# ── Outline REST API helpers ──────────────────────────────────────────

def api(endpoint: str, payload: dict = None) -> dict:
    url = f"{OUTLINE_URL}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {OUTLINE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload or {}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_collections() -> list:
    cols = []
    while True:
        data = api("collections.list", {"limit": 100, "offset": len(cols)})
        batch = data.get("data", [])
        cols.extend(batch)
        if len(batch) < 100:
            break
    return cols


def list_documents(collection_id: str) -> list:
    docs = []
    payload = {
        "collectionId": collection_id,
        "limit": 100,
        "sort": "title",
        "direction": "asc",
    }
    while True:
        data = api("documents.list", payload)
        batch = data.get("data", [])
        docs.extend(batch)
        if len(batch) < 100:
            break
        payload["offset"] = len(docs)
    return docs


def get_document(doc_id: str) -> dict:
    data = api("documents.info", {"id": doc_id})
    return data.get("data", {})


def download_attachment(attachment_id: str, save_path: Path) -> bool:
    url = f"{OUTLINE_URL}/api/attachments.redirect"
    headers = {"Authorization": f"Bearer {OUTLINE_API_KEY}"}
    try:
        resp = requests.get(
            url, params={"id": attachment_id}, headers=headers,
            timeout=30, allow_redirects=True,
        )
        if resp.status_code == 200 and len(resp.content) > 0:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(resp.content)
            return True
    except Exception as e:
        log.warning("    Download failed %s: %s", attachment_id, e)
    return False


# ── Media extraction ──────────────────────────────────────────────────

ATTACHMENT_RE = re.compile(
    r'!\[([^\]]*)\]\((/api/attachments\.redirect\?id=([a-f0-9-]+)[^)]*)\)'
)


def extract_attachments(text: str) -> list[tuple[str, str, str]]:
    return ATTACHMENT_RE.findall(text)


def rewrite_media_paths(text: str) -> str:
    def replacer(m):
        alt, _, att_id = m.group(1), m.group(2), m.group(3)
        return f"![{alt}](media/{att_id})"
    return ATTACHMENT_RE.sub(replacer, text)


# ── Backup logic ──────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def do_backup() -> tuple[str, str, str]:
    """
    Returns (text_archive_path, full_archive_path, summary_text).
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    work_dir = BACKUP_DIR / f"outline-backup-{ts}"
    work_dir.mkdir(parents=True, exist_ok=True)
    doc_count = 0
    media_count = 0
    col_count = 0

    log.info("Fetching collections...")
    collections = list_collections()
    log.info("Found %d collections", len(collections))

    for col in collections:
        col_name = col.get("name", "unnamed")
        col_dir = work_dir / sanitize(col_name)
        col_dir.mkdir(exist_ok=True)
        col_count += 1

        log.info("  Collection: %s", col_name)
        docs = list_documents(col["id"])
        log.info("    %d documents", len(docs))

        for doc in docs:
            title = doc.get("title", "untitled")
            doc_id = doc["id"]
            try:
                full = get_document(doc_id)
                text = full.get("text", "")

                # Extract & download media
                attachments = extract_attachments(text)
                media_dir = col_dir / "media"
                if attachments:
                    media_dir.mkdir(exist_ok=True)

                for alt, url, att_id in attachments:
                    ext = ".bin"
                    if "type=" in url:
                        try:
                            params = parse_qs(urlparse(url).query)
                            mime = params.get("type", [""])[0]
                            ext_map = {
                                "image/png": ".png", "image/jpeg": ".jpg",
                                "image/gif": ".gif", "image/webp": ".webp",
                                "application/pdf": ".pdf",
                            }
                            ext = ext_map.get(mime, ext)
                        except Exception:
                            pass
                    save_path = media_dir / f"{att_id}{ext}"
                    if not save_path.exists():
                        if download_attachment(att_id, save_path):
                            media_count += 1
                            log.info("    📎 %s%s", att_id[:8], ext)
                        time.sleep(0.2)

                # Rewrite media paths in markdown
                text = rewrite_media_paths(text)

                fname = sanitize(title) + ".md"
                (col_dir / fname).write_text(text, encoding="utf-8")
                doc_count += 1
                log.info("    ✓ %s", title)
            except Exception as e:
                log.warning("    ✗ %s: %s", title, e)
            time.sleep(0.3)

    # ── Full archive (text + media) → local only ──
    full_name = f"outline-full-{ts}.tar.gz"
    full_path = LOCAL_BACKUP_DIR / full_name
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(full_path, "w:gz") as tar:
        tar.add(work_dir, arcname=f"outline-backup-{ts}")
    full_mb = full_path.stat().st_size / 1024 / 1024
    log.info("Full archive: %s (%.1f MB)", full_name, full_mb)

    # ── Text-only archive (no media) → for Telegram ──
    text_dir = BACKUP_DIR / f"outline-text-{ts}"
    shutil.copytree(work_dir, text_dir, ignore=shutil.ignore_patterns("media"))
    text_name = f"outline-text-{ts}.tar.gz"
    text_path = BACKUP_DIR / text_name
    with tarfile.open(text_path, "w:gz") as tar:
        tar.add(text_dir, arcname=f"outline-text-{ts}")
    text_mb = text_path.stat().st_size / 1024 / 1024
    log.info("Text archive: %s (%.1f MB)", text_name, text_mb)

    # Cleanup temp dirs
    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(text_dir, ignore_errors=True)

    summary = (
        f"📦 Outline Backup — {ts}\n"
        f"• Collections: {col_count}\n"
        f"• Documents: {doc_count}\n"
        f"• Media files: {media_count}\n"
        f"• Text archive: {text_mb:.1f} MB (sent here)\n"
        f"• Full archive: {full_mb:.1f} MB (local only)"
    )
    return str(text_path), str(full_path), summary


# ── Telegram send ─────────────────────────────────────────────────────

def send_telegram(text: str, file_path: str = None):
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if TELEGRAM_THREAD_ID:
        payload["message_thread_id"] = int(TELEGRAM_THREAD_ID)

    requests.post(f"{base}/sendMessage", json=payload, timeout=15)

    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
        if size > 50 * 1024 * 1024:
            log.warning("File too large for Telegram (%.1f MB)", size / 1024 / 1024)
            return
        with open(file_path, "rb") as f:
            doc_payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": "Text-only backup"}
            if TELEGRAM_THREAD_ID:
                doc_payload["message_thread_id"] = int(TELEGRAM_THREAD_ID)
            requests.post(
                f"{base}/sendDocument", data=doc_payload,
                files={"document": (os.path.basename(file_path), f)},
                timeout=120,
            )
        log.info("Sent to Telegram")


# ── Cleanup ───────────────────────────────────────────────────────────

def cleanup_old():
    for d in [BACKUP_DIR, LOCAL_BACKUP_DIR]:
        if not d.exists():
            continue
        backups = sorted(
            d.glob("outline-*.tar.gz"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[KEEP_BACKUPS:]:
            log.info("Removing old backup: %s", old.name)
            old.unlink(missing_ok=True)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=== Outline Backup Start ===")
    try:
        text_path, full_path, summary = do_backup()
        send_telegram(summary, text_path)
        cleanup_old()
        log.info("=== Backup Complete ===")
    except Exception as e:
        log.error("Backup failed: %s", e, exc_info=True)
        try:
            send_telegram(f"❌ Outline backup failed:\n{e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
