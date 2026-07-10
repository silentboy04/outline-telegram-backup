# Outline → Telegram Backup

Automated backup of your [Outline](https://www.getoutline.com/) workspace to Telegram. Exports all documents as markdown, packages them into a tar.gz archive, and sends it to your Telegram chat.

## Features

- 📦 Exports all collections & documents as markdown
- 🗜️ Compressed tar.gz archive
- 📨 Sends backup + summary to Telegram
- 🗑️ Auto-cleanup of old backups (configurable)
- 🐳 Docker-ready, one-command setup
- ⏰ Schedule via host cron or any scheduler

## Quick Start

### 1. Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Pick a name (e.g. `Outline Backup Bot`)
4. Pick a username (e.g. `outline_backup_bot`)
5. Copy the **bot token** BotFather gives you

### 2. Get Your Chat ID

1. Add the bot to your target group/channel (as admin if private group)
2. Send any message in the group
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in browser
4. Find `"chat":{"id": -100...}` — that's your chat ID

Or use **@getmyid_bot** for your personal chat ID.

### 3. Get Outline API Key

**Cloud (app.getoutline.com):**
1. Go to **Settings** → **API**
2. Generate a new API token

**Self-hosted:**
1. Ensure API access is enabled in your Outline admin settings
2. Go to **Settings** → **API**
3. Generate a new API token

### 4. Configure & Run

```bash
# Clone
git clone https://github.com/YOUR_USER/outline-telegram-backup.git
cd outline-telegram-backup

# Configure
cp .env.example .env
# Edit .env with your tokens

# Run
docker compose up --build

# Or run directly (no Docker)
pip install requests
python backup.py
```

### 5. Schedule Weekly

Add to host crontab (`crontab -e`):

```bash
# Every Sunday at 03:00 UTC
0 3 * * 0 cd /path/to/outline-telegram-backup && docker compose up --build >> /var/log/outline-backup.log 2>&1
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OUTLINE_URL` | Yes | — | Outline instance URL |
| `OUTLINE_API_KEY` | Yes | — | Outline API token |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | — | Target chat/group ID |
| `KEEP_BACKUPS` | No | `4` | Max archives to keep |

## Troubleshooting

**"authentication_required"** — Your API key is invalid or API access is disabled on your Outline instance. For self-hosted, check admin settings.

**"File too large for Telegram"** — Telegram Bot API has a 50 MB limit. Your backup exceeded this. Consider archiving fewer collections.

## License

MIT
