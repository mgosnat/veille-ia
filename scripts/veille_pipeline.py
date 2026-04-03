import os, json, re, smtplib, ssl, time, requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SMTP_HOST  = os.environ.get("SMTP_HOST", "ssl0.ovh.net")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER  = os.environ["SMTP_USER"]
SMTP_PASS  = os.environ["SMTP_PASS"]
EMAIL_TO   = os.environ["EMAIL_TO"]
GITHUB_REPO_URL = os.environ.get("GITHUB_REPO_URL", "")

THEMES = {
    "agentique": {
        "label": "IA agentique",
        "color": "#16a34a",
        "keywords": [
            "agentic AI","multi-agent","AutoGen","CrewAI","LangGraph",
            "MCP protocol","agent framework","tool use","autonomous agent",
            "AI workflow","function calling","open source agents","reasoning model"
        ]
    },
    "gouvernance": {
        "label": "Gouvernance IA entreprise",
        "color": "#d97706",
        "keywords": [
            "AI governance","EU AI Act","ISO 42001","responsible AI",
            "AI compliance","AI policy","algorithmic bias","GPAI",
            "AI risk","AI accountability","AI regulation","AI audit"
        ]
    }
}

def fetch_insights(theme_id, theme):
    print(f"  -> Appel Claude API pour {theme['label']}...")
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": (
            f"Veille strategique sur \"{theme['label']}\". "
            f"Mots-cles: {', '.join(theme['keywords'])}. "
            "Recherche les dernieres actualites (24-48h). "
            "Retourne UNIQUEMENT un tableau JSON de 4 objets avec les champs: "
            "titre, resume (2-3 phrases en francais), source, url, pertinence (haute ou moyenne), categorie. "
            "JSON brut uniquement, sans markdown."
        )}]
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01"
    }
    for attempt in range(5):
        print(f"    tentative {attempt+1}/5...")
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers, json=payload, timeout=120
        )
        print(f"    status code: {resp.status_code}")
        if resp.status_code == 429:
            wait = 90 * (attempt + 1)
            print(f"    Rate limit 429 - pause {wait}s")
            time.sleep(wait)
            continue
        if not resp.ok:
            print(f"    Erreur {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        txt = (texts[-1] if texts else "").replace("```json","").replace("```","")
        m = re.search(r'\[[\s\S]*\]', txt)
        if m:
            return json.loads(m[0])
        print("    Pas de JSON valide dans la reponse")
        return []
    return []

def build_insight_card_html(item, color):
    pb = "#dcfce7" if item.get("pertinence") == "haute" else "#fef9c3"
    pt = "#15803d" if item.get("pertinence") == "haute" else "#854d0e"
    url = item.get("url","")
    titre = f'<a href="{url}" style="color:#111827;text-decoration:none;">{item.get("titre","")}</a>' if url else item.get("titre","")
    cat = item.get("categorie","")
    return f"""
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
        <p style="margin:0;font-size:15px;font-weight:600;line-height:1.4;color:#111827;">{titre}</p>
        <span style="background:{pb};color:{pt};font-size:11px;padding:2px 8px;border-radius:20px;white-space:nowrap;">{item.get("pertinence","")}</span>
      </div>
      <p style="margin:0 0 10px;font-size:13px;color:#4b5563;line-height:1.6;">{item.get("resume","")}</p>
      <div style="display:flex;gap:8px;align-items:center;">
        <span style="font-size:12px;color:#9ca3af;">{item.get("source","")}</span>
        {"<span style='background:#f3f4f6;color:#6b7280;font-size:11px;padding:1px 7px;border-radius:5px;'>"+cat+"</span>" if cat else ""}
      </div>
    </div>"""

def build_email_html(all_insights, date_str):
    sections = ""
    for tid, items in all_insights.items():
        theme = THEMES[tid]
        color = theme["color"]
        cards = "".join(build_insight_card_html(i, color) for i in items)
        sections += f"""
        <div style="margin-bottom:36px;">
          <div style="margin-bottom:16px;">
            <span style="background:{color}1a;color:{color};font-size:13px;font-weight:600;padding:5px 14px;border-radius:20px;">{theme["label"]}</span>
          </div>
          {cards}
        </div>"""
    return f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,sans-serif;">
  <div style="max-width:640px;margin:32px auto;">
    <div style="background:#111827;border-radius:12px 12px 0 0;padding:24px 28px;">
      <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;text-transform:uppercase;">Veille quotidienne</p>
      <h1 style="margin:0;font-size:22px;font-weight:700;color:#fff;">Tableau de veille IA</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#6b7280;">{date_str}</p>
    </div>
    <div style="background:#fff;border-radius:0 0 12px 12px;padding:28px;">
      {sections}
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">Veille automatisee ClinDiv · Claude AI + web search</p>
    </div>
  </div>
</body></html>"""

def send_email(html, date_str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Veille IA - {date_str}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"  Email envoye a {EMAIL_TO}")

def save_insights_json(all_insights):
    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "date_fr": datetime.now().strftime("%d/%m/%Y"),
        "insights": all_insights
    }
    with open("data/insights.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("  data/insights.json sauvegarde")

def main():
    date_str = datetime.now().strftime("%A %d %B %Y").capitalize()
    print(f"\nVeille IA - {date_str}\n")
    all_insights = {}
    for theme_id, theme in THEMES.items():
        print(f"[{theme['label']}]")
        insights = fetch_insights(theme_id, theme)
        all_insights[theme_id] = insights
        print(f"  -> {len(insights)} insights trouves\n")
        if len(THEMES) > 1:
            print("  -> Pause 15s entre themes...")
            time.sleep(15)
    save_insights_json(all_insights)
    print("[Email]")
    html = build_email_html(all_insights, date_str)
    send_email(html, date_str)
    print("\nPipeline termine avec succes.")

if __name__ == "__main__":
    main()
