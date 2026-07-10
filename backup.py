#!/usr/bin/env python3
"""
Outline → Telegram Backup (v2)
Uses native Outline export API per collection.
- Full zip (markdown + media) → saved locally
- Text-only summary → sent to Telegram
"""

import os
import sys
import json
import time
import shutil
import logging
import zipfile
import requests
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────
OUTLINE_URL = os.environ["OUTLINE_URL"].rstrip("/")
OUTLINE_API_KEY = os.environ["OUTLINE_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID", "")
LOCAL_BACKUP_DIR = Path(os.environ.get("LOCAL_BACKUP_DIR", "/data/backups/local"))
KEEP_BACKUPS = int(os.environ.get("KEEP_BACKUPS", "4"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("outline-backup")


# ── Outline API ───────────────────────────────────────────────────────

def api(endpoint: str, payload: dict = None) -> dict:
    url = f"{OUTLINE_URL}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {OUTLINE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload or {}, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_download(url: str) -> bytes:
    headers = {"Authorization": f"Bearer {OUTLINE_API_KEY}"}
    resp = requests.get(url, headers=headers, timeout=300, allow_redirects=True)
    resp.raise_for_status()
    return resp.content


def list_collections() -> list:
    return api("collections.list", {"limit": 100}).get("data", [])


def export_collection(col_id: str) -> str:
    """Trigger export for a collection, return fileOperation ID."""
    data = api("collections.export", {"id": col_id, "format": "outline-markdown"})
    op = data.get("data", {}).get("fileOperation", {})
    if not op.get("id"):
        raise RuntimeError(f"Export failed: {data}")
    return op["id"]


def wait_export(op_id: str, timeout: int = 300) -> dict:
    """Poll fileOperations.info until complete. Returns the fileOperation."""
    start = time.time()
    while time.time() - start < timeout:
        data = api("fileOperations.info", {"id": op_id})
        op = data.get("data", {})
        state = op.get("state")
        if state == "complete":
            return op
        elif state == "error":
            raise RuntimeError(f"Export error: {op.get('error')}")
        log.info("    ⏳ waiting for export... (%s)", state)
        time.sleep(3)
    raise TimeoutError(f"Export timed out after {timeout}s")


def download_export(op_id: str) -> bytes:
    """Download exported zip."""
    url = f"{OUTLINE_URL}/api/fileOperations.redirect?id={op_id}"
    return api_download(url)


# ── Backup logic ──────────────────────────────────────────────────────

def extract_text_only(zip_data: bytes, save_path: Path):
    """Extract zip but exclude uploads/ directories (media), re-zip as text-only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_zip = Path(tmpdir) / "src.zip"
        src_zip.write_bytes(zip_data)

        extract_dir = Path(tmpdir) / "extract"
        with zipfile.ZipFile(src_zip) as zf:
            zf.extractall(extract_dir)

        # Write text-only zip (exclude uploads/ dirs)
        with zipfile.ZipFile(save_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for f in sorted(extract_dir.rglob("*")):
                if f.is_file() and "uploads" not in str(f):
                    arcname = str(f.relative_to(extract_dir))
                    zout.write(f, arcname)


def do_backup() -> tuple[dict, str]:
    """
    Returns (collection_stats_dict, summary_text).
    Saves full zips to LOCAL_BACKUP_DIR.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    backup_dir = LOCAL_BACKUP_DIR / f"outline-export-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    collections = list_collections()
    log.info("Found %d collections", len(collections))

    stats = {}
    for col in collections:
        col_name = col["name"]
        col_id = col["id"]
        log.info("  📁 %s — exporting...", col_name)
        try:
            op_id = export_collection(col_id)
            op = wait_export(op_id)
            size = int(op.get("size", 0))
            log.info("  ✓ %s — %.1f MB", col_name, size / 1024 / 1024)

            # Download full zip
            zip_data = download_export(op_id)
            zip_name = f"{col_name.replace(' ', '_')}.zip"
            zip_path = backup_dir / zip_name
            zip_path.write_bytes(zip_data)

            # Count files in zip
            with zipfile.ZipFile(zip_path) as zf:
                total_files = len(zf.namelist())
                media_files = sum(1 for n in zf.namelist() if "uploads" in n)

            stats[col_name] = {
                "files": total_files,
                "media": media_files,
                "size_mb": len(zip_data) / 1024 / 1024,
                "zip_path": str(zip_path),
            }
        except Exception as e:
            log.error("  ✗ %s: %s", col_name, e)
            stats[col_name] = {"error": str(e)}
        time.sleep(1)

    total_files = sum(s.get("files", 0) for s in stats.values())
    total_media = sum(s.get("media", 0) for s in stats.values())
    total_size = sum(s.get("size_mb", 0) for s in stats.values())

    lines = [
        f"📦 Outline Backup — {ts}",
        f"• Collections: {len(stats)}",
        f"• Total files: {total_files} ({total_media} media)",
        f"• Total size: {total_size:.1f} MB",
        "",
    ]
    for col_name, s in stats.items():
        if "error" in s:
            lines.append(f"❌ {col_name}: {s['error']}")
        else:
            lines.append(f"  ✓ {col_name}: {s['files']} files ({s['media']} media), {s['size_mb']:.1f} MB")
    lines.append(f"\n💾 Saved to: {backup_dir}")

    summary = "\n".join(lines)
    log.info("Archive dir: %s", backup_dir)
    return stats, summary


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
            log.info("File too large for Telegram (%.1f MB), skipping", size / 1024 / 1024)
            return
        with open(file_path, "rb") as f:
            doc_payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": "Full backup archive"}
            if TELEGRAM_THREAD_ID:
                doc_payload["message_thread_id"] = int(TELEGRAM_THREAD_ID)
            requests.post(
                f"{base}/sendDocument", data=doc_payload,
                files={"document": (os.path.basename(file_path), f)},
                timeout=120,
            )
        log.info("Sent file to Telegram")


# ── Cleanup ───────────────────────────────────────────────────────────

def cleanup_old():
    if not LOCAL_BACKUP_DIR.exists():
        return
    backups = sorted(
        LOCAL_BACKUP_DIR.glob("outline-export-*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[KEEP_BACKUPS:]:
        log.info("Removing old backup: %s", old.name)
        shutil.rmtree(old, ignore_errors=True)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    LOCAL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    log.info("=== Outline Backup Start ===")
    try:
        stats, summary = do_backup()
        send_telegram(summary)
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
