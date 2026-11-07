# ContextOS

A small website that reads your Gmail, Slack and Discord and tells you what happened today.

It runs on your own computer. Open it in the morning and you get a short briefing:

- **Needs you**: things you should reply to or act on
- **Important**: things you'd be upset to miss
- **FYI**: everything else worth a line

Every item links back to the original message, so you can check it yourself.

---

## Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
contextos web
```

Your browser opens at **http://localhost:8000**. Go to **Sources** and:

1. Paste your Anthropic API key (get one at [platform.claude.com](https://platform.claude.com)).
2. Connect at least one source (steps below).
3. Go back to **Today** and press **Write my briefing**.

After that, ContextOS syncs every 15 minutes and writes a new briefing each morning. You only need to open the page.

---

## Pages

| Page | What it's for |
|---|---|
| **Today** | Your briefing. Mark things **Done**, push them to **Tomorrow**, or rate them 👍 / 👎. |
| **Ask** | Ask a question like "what did Priya say about the contract?" and get an answer with links. |
| **History** | Every past briefing. |
| **Sources** | Connect accounts, add keys, set your name and what matters to you. |

---

## Connecting sources

You only do this once for each source.

<details>
<summary><b>Gmail</b> (about 10 minutes)</summary>

1. Open [console.cloud.google.com](https://console.cloud.google.com) and create a project.
2. Search for **Gmail API** and click **Enable**.
3. Open **OAuth consent screen**, choose **External**, fill in the name and your email, and add yourself under **Test users**.
4. Open **Credentials → Create credentials → OAuth client ID**, choose **Desktop app**, and download the JSON file.
5. In ContextOS, go to **Sources**, upload that file, then press **Connect Gmail**.

ContextOS can only read your mail, never send or delete it. Google asks you to sign in again every 7 days while the app is in test mode; Sources will tell you when.
</details>

<details>
<summary><b>Slack</b> (about 3 minutes)</summary>

1. Open [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch** and pick your workspace.
2. Under **OAuth & Permissions → User Token Scopes**, add:
   `channels:history` `channels:read` `groups:history` `groups:read` `im:history` `im:read` `mpim:history` `mpim:read` `users:read`
3. Click **Install to Workspace** and copy the token that starts with `xoxp-`.
4. Paste it into **Sources → Slack user token**.

On a work Slack, check that your company is OK with this first.
</details>

<details>
<summary><b>Discord</b> (about 3 minutes, servers only)</summary>

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application → Bot** → **Reset Token** and copy the token.
2. On the same page, turn on **Message Content Intent**.
3. Under **OAuth2 → URL Generator**, tick `bot`, then **View Channels** and **Read Message History**. Open the link and add the bot to your servers.
4. Paste the token into **Sources → Discord bot token**.

Discord doesn't let apps read your private DMs, so only servers are included.
</details>

---

## How it works

```
Gmail, Slack, Discord
        │  every 15 min: fetch new messages
        ▼
   Local database  (~/.contextos)
        │
        ├── Today:  pick today's messages → drop the noise → Claude writes the briefing
        │           → every claim must cite a real message, or it's flagged
        │
        └── Ask:    Claude searches your messages with tools until it can answer
```

A few things worth knowing:

- **Noise is removed before Claude sees it.** Promotions and muted channels are skipped, and newsletters and bots are cut to one line each. That keeps briefings cheap and focused. A typical day costs a few cents.
- **Busy days are handled in two steps.** If there's too much to read at once, a faster model summarizes it in parts first.
- **Your 👍 / 👎 votes are saved**, along with anything you type into "Did it miss something?". Over time that becomes a test set for making the briefing better.

If you're reading the code to learn, start with `contextos/digest.py` (how the briefing is made) and `contextos/ask.py` (how the question answering works).

---

## Privacy

- Everything is stored on your computer in `~/.contextos`. Keys are saved there with owner-only access.
- The website only accepts requests from your own computer.
- To write a briefing, the text of the day's messages is sent to Claude.

---

## For developers

```bash
pip install -e ".[dev]"
pytest                      # runs offline, no keys needed
contextos today             # the same briefing, printed in the terminal
contextos ask "question"
contextos status
```

The earlier version of this project is saved at git tag `contextos-prototype`.
