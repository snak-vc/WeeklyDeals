# 🏪 Snak.vc — Marketplace Funding Weekly

A GitHub Action that runs every **Sunday at 8 AM ET**, searches the web for marketplace startup funding activity from the past 7 days (via Claude AI), and emails a branded HTML newsletter via Gmail.

---

## 📁 File Structure

```
snak-newsletter/
├── .github/
│   └── workflows/
│       └── marketplace_newsletter.yml   ← the GitHub Action
├── scripts/
│   └── generate_and_send.py             ← the main script
└── README.md
```

---

## 🚀 Setup (one-time, ~10 minutes)

### Step 1 — Create a GitHub repo

1. Go to [github.com](https://github.com) → **New repository**
2. Name it `snak-newsletter` (or anything you like)
3. Upload all these files keeping the same folder structure

---

### Step 2 — Get a Gmail App Password

Gmail requires an "App Password" (not your regular password) for SMTP access.

1. Go to your Google Account → **Security**
2. Make sure **2-Step Verification** is ON
3. Search for "App passwords" → create one
4. Name it "Snak Newsletter" → copy the 16-character password

---

### Step 3 — Get an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. **API Keys** → **Create Key**
3. Copy it — you won't see it again

---

### Step 4 — Add secrets to GitHub

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these three secrets:

| Secret Name         | Value                                      |
|---------------------|--------------------------------------------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key                     |
| `GMAIL_ADDRESS`     | Your Gmail address (e.g. you@gmail.com)    |
| `GMAIL_APP_PASSWORD`| The 16-character App Password from Step 2  |

---

### Step 5 — Edit recipients

Open `scripts/generate_and_send.py` and update the `RECIPIENTS` list near the top:

```python
RECIPIENTS = [
    "you@example.com",
    "teammate@example.com",
]
```

---

### Step 6 — Test it manually

1. In your repo → **Actions** tab
2. Click **"Snak.vc — Marketplace Funding Weekly"**
3. Click **"Run workflow"** → **Run workflow**
4. Watch the logs — you should receive the email within ~2 minutes

---

## 📅 Schedule

The action runs automatically every **Sunday at 12:00 UTC (8:00 AM ET)**.

To change the time, edit the `cron` line in `.github/workflows/marketplace_newsletter.yml`:

```yaml
- cron: "0 12 * * 0"   # minute hour day month weekday
```

Examples:
- `"0 14 * * 0"` → Sundays at 9 AM ET
- `"0 16 * * 0"` → Sundays at 11 AM ET

---

## 🔍 Preview

Every run saves `newsletter_preview.html` as a GitHub Actions artifact (kept 14 days).
Find it under **Actions** → your run → **Artifacts**.

---

## 💡 Customization

| What to change           | Where                                       |
|--------------------------|---------------------------------------------|
| Recipients               | `RECIPIENTS` list in `generate_and_send.py` |
| Brand color              | `BRAND_COLOR` in `generate_and_send.py`     |
| Deal sources / focus     | `SYSTEM` prompt in `generate_and_send.py`   |
| Send time                | `cron` in `marketplace_newsletter.yml`      |
