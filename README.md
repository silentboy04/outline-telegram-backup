# Outline → Telegram Backup

Automated backup of your [Outline](https://www.getoutline.com/) workspace. Exports all documents as markdown + media.

## How It Works

- **Text-only archive** (markdown) → sent to Telegram
- **Full archive** (markdown + media files) → saved locally only

Telegram has a 50 MB limit, so media-heavy workspaces use local storage for the complete backup.

## Quick Start

### 1. Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Copy the bot token

### 2. Get Your Chat ID

1. Add the bot to your group (as admin)
2. Send any message
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Find `"chat":{"id": -100...}` — that's your chat ID

### 3. Get Outline API Key

Go to your Outline instance → **Settings** → **API** → Generate token

### 4. Run

```bash
git clone https://github.com/silentboy04/outline-telegram-backup.git
cd outline-telegram-backup
cp .env.example .env
# Edit .env with your tokens
docker compose up --build
```

### 5. Schedule Weekly (crontab)

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
| `KEEP_BACKUPS` | No | Max archives to keep (default: 4) |

## License

MIT
