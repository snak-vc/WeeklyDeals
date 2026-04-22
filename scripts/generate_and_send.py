#!/usr/bin/env python3
"""
SNAK — Weekly Marketplace Funding Newsletter
Calls Claude API (with web search), generates branded HTML, sends via Gmail SMTP.
"""

import os
import json
import smtplib
import re
import sys
import pickle
import base64
import urllib.parse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
import gspread
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ── Recipients ───────────────────────────────────────────────────────────────
RECIPIENTS = [
    "sonia@snak.vc",          # ← replace with real addresses
    "adam@snak.vc",
]

# ── Deduplication ─────────────────────────────────────────────────────────────
SEEN_DEALS_FILE = "seen_deals.json"
SPREADSHEET_NAME = "SNAK Weekly Marketplace Deals"
SHEET_HEADERS = ["Company Name", "Description", "Round", "Funding Amount", "HQ Location"]


def load_seen_deals() -> set[str]:
    if not os.path.exists(SEEN_DEALS_FILE):
        return set()
    try:
        with open(SEEN_DEALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x) for x in data}
    except (OSError, json.JSONDecodeError):
        pass
    return set()


def save_seen_deals(seen: set[str]) -> None:
    with open(SEEN_DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, indent=2)
        f.write("\n")


def make_deal_key(deal: dict) -> str:
    def norm(v: object) -> str:
        return " ".join(str(v or "").lower().split())

    company = norm(deal.get("company"))
    amount = norm(deal.get("amount"))
    round_ = norm(deal.get("round"))
    return f"{company}|{amount}|{round_}"


def parse_amount(amount_str: str) -> str:
    if not amount_str:
        return amount_str

    s = str(amount_str).strip()
    s_clean = s.replace("$", "").replace(",", "").strip()
    if not s_clean:
        return amount_str

    suffix = ""
    if s_clean and s_clean[-1].isalpha():
        suffix = s_clean[-1].lower()
        s_clean = s_clean[:-1].strip()

    try:
        num = float(s_clean)
    except ValueError:
        return amount_str

    multiplier = {"": 1.0, "k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}.get(suffix)
    if multiplier is None:
        return amount_str

    dollars = num * multiplier
    if dollars < 500_000:
        return f"${int(round(dollars / 1_000.0)):d}k"

    millions = dollars / 1_000_000.0
    return f"${millions:,.1f}M"


def get_google_credentials() -> Credentials:
    token_b64 = os.environ["GOOGLE_TOKEN_PICKLE"]
    raw = base64.b64decode(token_b64)
    creds = pickle.loads(raw)
    return creds


def get_or_create_sheet():
    creds = get_google_credentials()

    # Keep explicit service available (useful for future formatting/metadata)
    _sheets_service = build("sheets", "v4", credentials=creds)  # noqa: F841

    client = gspread.authorize(creds)
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(SPREADSHEET_NAME)

    worksheet = spreadsheet.sheet1
    existing = worksheet.row_values(1)
    if [c.strip() for c in existing if c.strip()] != SHEET_HEADERS:
        worksheet.clear()
        worksheet.append_row(SHEET_HEADERS, value_input_option="RAW")
        worksheet.freeze(rows=1)
        worksheet.format("1:1", {"textFormat": {"bold": True}})

    return worksheet


def _normalize_round(round_str: str) -> str:
    r = " ".join(str(round_str or "").strip().split()).lower()
    if not r:
        return ""
    if "pre" in r and "seed" in r:
        return "Pre-Seed"
    if r == "seed" or " seed" in r or r.endswith("seed"):
        return "Seed"
    for letter in ["a", "b", "c"]:
        if f"series {letter}" in r or f"serie {letter}" in r:
            return f"Series {letter.upper()}"
    if "growth" in r or "late" in r:
        return "Growth"
    if "m&a" in r or "acqui" in r or "acquisition" in r or "merge" in r:
        return "M&A"
    if "ipo" in r:
        return "IPO"
    return round_str


def _truncate_sentences(text: str, max_sentences: int = 3) -> str:
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(parts[:max_sentences]).strip()


def _safe_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    parsed = urllib.parse.urlparse(u)
    if not parsed.scheme:
        u = "https://" + u
        parsed = urllib.parse.urlparse(u)
    if parsed.scheme not in {"http", "https"}:
        return ""
    return u


def write_deals_to_sheet(worksheet, deals: list[dict], seen: set[str]):
    rows = []
    for d in deals or []:
        if make_deal_key(d) in seen:
            continue

        name = str(d.get("company", "") or "").strip()
        website_url = _safe_url(str(d.get("website_url", "") or ""))
        if website_url and name:
            safe_name = name.replace('"', '""')
            company_cell = f'=HYPERLINK("{website_url}","{safe_name}")'
        else:
            company_cell = name

        description = _truncate_sentences(d.get("description", ""), 3)
        round_norm = _normalize_round(d.get("round", ""))
        amount_disp = parse_amount(str(d.get("amount", "") or ""))
        hq = " ".join(str(d.get("hq_location", "") or "").strip().split())

        rows.append([company_cell, description, round_norm, amount_disp, hq])

    if rows:
        worksheet.insert_rows(rows, row=2, value_input_option="USER_ENTERED")


# ── Snak brand ───────────────────────────────────────────────────────────────
BRAND_COLOR   = "#385892"
BRAND_LIGHT   = "#4a6ea8"
BRAND_DARK    = "#263d66"
BRAND_BG      = "#f0f4fa"
ACCENT_GREEN  = "#1e7e4a"
ACCENT_PURPLE = "#6b3fa0"
ACCENT_ORANGE = "#c45c1a"

STAGE_META = {
    "IPO / M&A":        {"color": ACCENT_GREEN,  "emoji": "🏛️"},
    "Growth":           {"color": BRAND_COLOR,    "emoji": "🚀"},
    "Early":            {"color": ACCENT_PURPLE,  "emoji": "🌱"},
    "Pre-Seed / Seed":  {"color": ACCENT_ORANGE,  "emoji": "🌰"},
}
STAGE_ORDER = ["IPO / M&A", "Growth", "Early", "Pre-Seed / Seed"]

# ── Date helpers ──────────────────────────────────────────────────────────────
today      = datetime.now()
week_start = today - timedelta(days=7)
DATE_RANGE = f"{week_start.strftime('%B %d')} – {today.strftime('%B %d, %Y')}"
SUBJECT    = f"💰 SNAK | Weekly Marketplace Funding · {today.strftime('%b %d, %Y')}"

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM = """You are a venture capital research analyst for Snak.vc, a firm focused on marketplace businesses.
Find ALL marketplace startup funding announcements and M&A activity published in the PAST 7 DAYS ONLY.

A 'marketplace' connects buyers and sellers or two-sided networks: gig economy, B2B, consumer, real estate,
fintech, healthcare, labor, freight, creator economy, and more. Cast the widest possible net.

Sources: TechCrunch, The Information, Forbes, WSJ, NY Times, and company press releases.

CRITICAL: Only include deals where the news article was published within the last 7 days.
Never fabricate companies or deals.

For each deal, include:
- website_url: the company's homepage URL (not an article URL)
- hq_location: headquarters location in "City, State" (or "City, Country" for international)

Return ONLY valid JSON — no markdown fences, no preamble:
{
  "week_ending": "April 27, 2025",
  "total_deals": 8,
  "total_capital": "$1.2B",
  "deals": [
    {
      "company": "Acme Markets",
      "stage": "Growth",
      "amount": "$50M",
      "round": "Series B",
      "category": "B2B Marketplace",
      "website_url": "https://acmemarkets.com",
      "hq_location": "San Francisco, CA",
      "description": "One sentence on what the company does.",
      "why_it_matters": "One sentence on the significance of this deal.",
      "notable_investors": ["Andreessen Horowitz", "Sequoia"],
      "source": "TechCrunch",
      "source_url": "https://techcrunch.com/...",
      "announced_date": "April 23, 2025"
    }
  ]
}
stage must be exactly one of: "IPO / M&A", "Growth", "Early", "Pre-Seed / Seed"
"""


# ── 1. Fetch deals via Claude + web search ────────────────────────────────────
def fetch_deals() -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_msg = (
        f"Today is {today.strftime('%B %d, %Y')}. Search for ALL marketplace startup funding "
        f"announcements and M&A activity published between "
        f"{week_start.strftime('%B %d, %Y')} and {today.strftime('%B %d, %Y')}. "
        "Return every deal you can find in this 7-day window."
    )

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        system=SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_msg}],
    )

    # Extract JSON from the final text block
    full_text = "".join(b.text for b in response.content if hasattr(b, "text"))
    match = re.search(r"\{[\s\S]*\}", full_text)
    if not match:
        raise ValueError("No JSON found in Claude response")
    return json.loads(match.group(0))


# ── 2. Build HTML email ───────────────────────────────────────────────────────
def build_html(data: dict) -> str:
    deals      = data.get("deals", [])
    total      = data.get("total_deals", len(deals))
    capital    = data.get("total_capital", "N/A")
    week_ending = data.get("week_ending") or today.strftime("%B %d, %Y")

    # Group by stage
    grouped = {s: [d for d in deals if d.get("stage") == s] for s in STAGE_ORDER}

    # ── stat pills ────────────────────────────────────────────────────────────
    stats_html = f"""
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td align="center" style="padding:0 8px">
          <div style="background:#fff;border:1px solid #dce6f5;border-radius:10px;padding:14px 24px;display:inline-block;min-width:120px">
            <div style="font-size:26px;font-weight:800;color:{BRAND_COLOR};font-family:Georgia,serif">{total}</div>
            <div style="font-size:11px;color:#8a9ab5;text-transform:uppercase;letter-spacing:1px;margin-top:2px">Deals Found</div>
          </div>
        </td>
        <td align="center" style="padding:0 8px">
          <div style="background:#fff;border:1px solid #dce6f5;border-radius:10px;padding:14px 24px;display:inline-block;min-width:120px">
            <div style="font-size:26px;font-weight:800;color:{ACCENT_PURPLE};font-family:Georgia,serif">{len([d for d in deals if d.get('stage')=='IPO / M&A'])}</div>
            <div style="font-size:11px;color:#8a9ab5;text-transform:uppercase;letter-spacing:1px;margin-top:2px">IPO / M&amp;A</div>
          </div>
        </td>
      </tr>
    </table>"""

    # ── deal card builder ─────────────────────────────────────────────────────
    def deal_card(d: dict, accent: str) -> str:
        investors = d.get("notable_investors", [])[:3]
        inv_pills = "".join(
            f'<span style="display:inline-block;background:#eef2f8;color:#5a6a85;'
            f'font-size:10px;padding:3px 9px;border-radius:20px;margin:2px 3px 2px 0;'
            f'font-family:monospace">{i}</span>'
            for i in investors
        )
        source_url = d.get("source_url", "#")
        source_link = (
            f'<a href="{source_url}" style="color:{accent};font-size:11px;text-decoration:none;font-family:monospace">'
            f'{d.get("source","Source")} ↗</a>'
            if source_url and source_url != "#"
            else f'<span style="color:#aaa;font-size:11px;font-family:monospace">{d.get("source","")}</span>'
        )
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px">
          <tr>
            <td style="background:#fff;border:1px solid #dce6f5;border-left:4px solid {accent};
                        border-radius:0 10px 10px 0;padding:18px 20px">
              <!-- top row -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px">
                <tr>
                  <td>
                    <span style="font-family:Georgia,serif;font-size:17px;font-weight:700;color:#1a2a3a">{d.get('company','')}</span>
                    <span style="display:inline-block;background:{accent}18;color:{accent};
                                 font-size:10px;padding:2px 8px;border-radius:20px;margin-left:8px;
                                 font-family:monospace;vertical-align:middle">{d.get('category','')}</span>
                  </td>
                  <td align="right" style="white-space:nowrap">
                    <span style="font-family:Georgia,serif;font-size:18px;font-weight:800;color:{accent}">{d.get('amount','')}</span>
                    <span style="display:block;font-family:monospace;font-size:10px;color:#aaa;text-align:right">{d.get('round','')}</span>
                  </td>
                </tr>
              </table>
              <!-- description -->
              <p style="font-size:13px;color:#4a5568;line-height:1.6;margin:0 0 10px;font-family:Georgia,serif">{d.get('description','')}</p>
              <!-- why it matters -->
              <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px">
                <tr>
                  <td style="background:{accent}0d;border-left:3px solid {accent};
                              padding:8px 12px;border-radius:0 6px 6px 0">
                    <span style="font-family:monospace;font-size:10px;text-transform:uppercase;
                                 letter-spacing:1px;color:{accent};display:block;margin-bottom:3px">Why it matters</span>
                    <span style="font-size:12px;color:#5a6a7a;line-height:1.55;font-family:Georgia,serif">{d.get('why_it_matters','')}</span>
                  </td>
                </tr>
              </table>
              <!-- footer row -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>{inv_pills}</td>
                  <td align="right" style="white-space:nowrap;vertical-align:middle">
                    <span style="font-family:monospace;font-size:10px;color:#bbb;margin-right:10px">{d.get('announced_date','')}</span>
                    {source_link}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>"""

    # ── stage sections ────────────────────────────────────────────────────────
    sections_html = ""
    for stage in STAGE_ORDER:
        stage_deals = grouped.get(stage, [])
        if not stage_deals:
            continue
        meta   = STAGE_META[stage]
        accent = meta["color"]
        emoji  = meta["emoji"]
        cards  = "".join(deal_card(d, accent) for d in stage_deals)
        sections_html += f"""
        <!-- Stage: {stage} -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px">
          <tr>
            <td style="padding-bottom:10px;border-bottom:2px solid {accent}33">
              <span style="font-family:monospace;font-size:11px;text-transform:uppercase;
                           letter-spacing:2px;color:{accent};font-weight:700">
                {emoji}&nbsp; {stage}
              </span>
              <span style="float:right;font-family:monospace;font-size:10px;
                           background:{accent}18;color:{accent};padding:2px 10px;
                           border-radius:20px">{len(stage_deals)} deal{'s' if len(stage_deals)!=1 else ''}</span>
            </td>
          </tr>
          <tr><td style="padding-top:14px">{cards}</td></tr>
        </table>"""

    no_deals_html = """
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td align="center" style="padding:48px 0;color:#aaa;font-family:Georgia,serif">
              No marketplace deals found this week. Check back next Sunday.
            </td>
          </tr>
        </table>""" if total == 0 else ""

    # ── full email ────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{SUBJECT}</title>
</head>
<body style="margin:0;padding:0;background:#e8edf5;font-family:Georgia,serif">

  <!-- Wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#e8edf5;padding:32px 0">
    <tr>
      <td align="center">
        <table width="100%" style="max-width:680px" cellpadding="0" cellspacing="0">

          <!-- ── HEADER ───────────────────────────────────────────────────── -->
          <tr>
            <td style="background:#ffffff;padding:16px 24px 14px;border-radius:14px 14px 0 0;border-bottom:1px solid #dce6f5">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="vertical-align:top">
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;letter-spacing:3px;text-transform:uppercase;color:#0f172a;line-height:1.1">
                      SNAK
                    </div>
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;font-weight:300;letter-spacing:1.6px;text-transform:uppercase;color:#6b7280;line-height:1.2;margin-top:4px">
                      Venture Partners
                    </div>
                  </td>
                  <td align="right" style="vertical-align:top;text-align:right">
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:2.4px;text-transform:uppercase;color:#0f172a;line-height:1.1">
                      Marketplace Funding Weekly
                    </div>
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:400;color:#334155;line-height:1.2;margin-top:6px">
                      {week_ending}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── HEADER BANNER ─────────────────────────────────────────────── -->
          <tr>
            <td style="background:{BRAND_COLOR};padding:10px 24px;border-bottom:1px solid #dce6f5">
              <div style="font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:2.6px;text-transform:uppercase;color:#ffffff;line-height:1.1">
                Weekly Funding Report
              </div>
            </td>
          </tr>

          <!-- ── STATS BAR ─────────────────────────────────────────────────── -->
          <tr>
            <td style="background:{BRAND_BG};padding:20px 40px;border-bottom:1px solid #dce6f5">
              {stats_html}
            </td>
          </tr>

          <!-- ── BODY ──────────────────────────────────────────────────────── -->
          <tr>
            <td style="background:{BRAND_BG};padding:28px 40px">
              {sections_html or no_deals_html}
            </td>
          </tr>

          <!-- ── FOOTER ────────────────────────────────────────────────────── -->
          <tr>
            <td style="background:{BRAND_DARK};padding:24px 40px;border-radius:0 0 14px 14px;text-align:center">
              <p style="margin:0 0 6px;font-family:Georgia,serif;font-size:14px;font-weight:700;color:#a8c4e8">
                snak.vc
              </p>
              <p style="margin:0 0 10px;font-family:monospace;font-size:10px;color:#607090;
                         letter-spacing:0.5px;text-transform:uppercase">
                Marketplace Funding Weekly · Powered by Claude AI + Web Search
              </p>
              <p style="margin:0;font-family:monospace;font-size:10px;color:#4a5a72">
                Sources: TechCrunch · The Information · Forbes · WSJ · NYT · Press Releases
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ── 3. Send via Gmail SMTP ─────────────────────────────────────────────────────
def send_email(html: str):
    sender  = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = SUBJECT
    msg["From"]    = f"SNAK Research <{sender}>"
    msg["To"]      = ", ".join(RECIPIENTS)

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, RECIPIENTS, msg.as_string())

    print(f"✅  Email sent to {len(RECIPIENTS)} recipient(s)")


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"🔍  Fetching marketplace deals for {DATE_RANGE} …")
    data = fetch_deals()
    print(f"📦  Found {data.get('total_deals', 0)} deals · {data.get('total_capital', 'N/A')} total capital")

    seen = load_seen_deals()
    original_deals = data.get("deals", []) or []
    new_deals = [d for d in original_deals if make_deal_key(d) not in seen]
    data["deals"] = new_deals
    data["total_deals"] = len(new_deals)

    if not new_deals:
        print("No new deals this week")
        if not os.path.exists(SEEN_DEALS_FILE):
            save_seen_deals(seen)
        sys.exit(0)

    html = build_html(data)

    # Save a local copy for debugging / preview
    with open("newsletter_preview.html", "w") as f:
        f.write(html)
    print("💾  Preview saved → newsletter_preview.html")

    send_email(html)

    worksheet = get_or_create_sheet()
    write_deals_to_sheet(worksheet, new_deals, seen)

    for d in new_deals:
        seen.add(make_deal_key(d))
    save_seen_deals(seen)