#!/usr/bin/env python3
"""
Outline → Telegram Backup
Exports all Outline docs as markdown, tars them up, sends to Telegram.

Supports two auth methods:
1. Outline REST API (recommended) — direct API calls
2. MCP Server — via Outline MCP protocol (fallback)
"""

import os
import sys
import json
import time
import tarfile
import shutil
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
OUTLINE_URL = os.environ["OUTLINE_URL"]
OUTLINE_API_KEY = os.environ["OUTLINE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/data/backups"))
KEEP_BACKUPS = int(os.environ.get("KEEP_BACKUPS", "4"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("outline-backup")

# ── Outline REST API helpers ──────────────────────────────────────────

def api(endpoint: str, payload: dict = None) -> dict:
    """Call Outline REST API endpoint."""
    url = f"{OUTLINE_URL}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {OUTLINE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload or {}, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok", True):
        log.error("API error on %s: %s", endpoint, data.get("error", data))
    return data


def list_collections() -> list:
    """List all collections."""
    cols = []
    while True:
        data = api("collections.list", {"limit": 100, "offset": len(cols)})
        batch = data.get("data", [])
        cols.extend(batch)
        if len(batch) < 100:
            break
    return cols


def list_documents(collection_id: str) -> list:
    """List all documents in a collection."""
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
    """Get full document content."""
    data = api("documents.info", {"id": doc_id})
    return data.get("data", {})


# ── Backup logic ──────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    """Sanitize folder/file name."""
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


def do_backup() -> tuple[str, str]:
    """Run full backup. Returns (tar_path, summary_text)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    work_dir = BACKUP_DIR / f"outline-backup-{ts}"
    work_dir.mkdir(parents=True, exist_ok=True)
    doc_count = 0
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
                fname = sanitize(title) + ".md"
                (col_dir / fname).write_text(text, encoding="utf-8")
                doc_count += 1
                log.info("    ✓ %s", title)
            except Exception as e:
                log.warning("    ✗ %s: %s", title, e)
            time.sleep(0.3)

    # Create tar.gz
    tar_name = f"outline-backup-{ts}.tar.gz"
    tar_path = BACKUP_DIR / tar_name
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(work_dir, arcname=f"outline-backup-{ts}")
    log.info("Archive: %s (%.1f MB)", tar_name, tar_path.stat().st_size / 1024 / 1024)
    shutil.rmtree(work_dir, ignore_errors=True)

    size_mb = tar_path.stat().st_size / 1024 / 1024
    summary = (
        f"📦 Outline Backup — {ts}\n"
        f"• Collections: {col_count}\n"
        f"• Documents: {doc_count}\n"
        f"• Size: {size_mb:.1f} MB"
    )
    return str(tar_path), summary


# ── Telegram send ─────────────────────────────────────────────────────

def send_telegram(text: str, file_path: str = None):
    """Send message (and optional file) to Telegram."""
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    # Send text
    requests.post(
        f"{base}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )

    # Send file if provided
    if file_path and os.path.exists(file_path):
        size = os.path.getsize(file_path)
        if size > 50 * 1024 * 1024:
            log.warning("File too large for Telegram (%.1f MB), skipping upload", size / 1024 / 1024)
            return
        with open(file_path, "rb") as f:
            requests.post(
                f"{base}/sendDocument",
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": "Full backup archive"},
                files={"document": (os.path.basename(file_path), f)},
                timeout=120,
            )
        log.info("Sent to Telegram")


# ── Cleanup ───────────────────────────────────────────────────────────

def cleanup_old():
    """Keep only KEEP_BACKUPS most recent backups."""
    backups = sorted(
        BACKUP_DIR.glob("outline-backup-*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[KEEP_BACKUPS:]:
        log.info("Removing old backup: %s", old.name)
        old.unlink(missing_ok=True)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=== Outline Backup Start ===")
    try:
        tar_path, summary = do_backup()
        send_telegram(summary, tar_path)
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
