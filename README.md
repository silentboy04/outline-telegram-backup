# Outline → Telegram Backup

Automated backup of your [Outline](https://www.getoutline.com/) workspace using the native export API.

## How It Works

Uses Outline's `collections.export` API to export each collection as a complete zip:
- ✅ Markdown documents (current state)
- ✅ All media files (images, attachments)
- ✅ Proper folder structure (collections → documents → uploads)

Full zips saved locally. Summary sent to Telegram.

## Quick Start

### 1. Create a Telegram Bot

Search **@BotFather** → `/newbot` → copy token

### 2. Get Chat ID

Add bot to your group (as admin) → send message → open `https://api.telegram.org/bot<TOKEN>/getUpdates` → find `"chat":{"id": -100...}`

### 3. Get Outline API Key

Settings → API → Generate token

### 4. Run

```bash
git clone https://github.com/silentboy04/outline-telegram-backup.git
cd outline-telegram-backup
cp .env.example .env
# edit .env
docker compose up --build
```

### 5. Schedule Weekly

```bash
0 3 * * 0 cd /path/to/outline-telegram-backup && docker compose up --build
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OUTLINE_URL` | Yes | Outline instance URL |
| `OUTLINE_API_KEY` | Yes | Outline API token |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | Target chat/group ID |
| `TELEGRAM_THREAD_ID` | No | Topic/thread ID for supergroups |
| `LOCAL_BACKUP_DIR` | No | Local path for full backups (default: /data/backups/local) |
| `KEEP_BACKUPS` | No | Max backup sets to keep (default: 4) |

## Limits

- Native full-workspace export has a 3.82 GB limit (Outline server-side). This tool exports per-collection, avoiding that limit.
- Telegram file upload limit: 50 MB. Full zips >50 MB are saved locally only; summary goes to Telegram.

## License

MIT
