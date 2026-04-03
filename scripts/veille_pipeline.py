"""
Pipeline de veille IA - ClinDiv / Muriel Gosnat
GitHub Actions + Claude API (web search) + OVH SMTP
Génère insights.json + envoie email digest quotidien
"""

import os
import json
import re
import smtplib
import ssl
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ─── Configuration ───────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SMTP_HOST         = os.environ.get("SMTP_HOST", "ssl0.ovh.net")
SMTP_PORT         = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER         = os.environ["SMTP_USER"]
SMTP_PASS         = os.environ["SMTP_PASS"]
EMAIL_TO          = os.environ["EMAIL_TO"]
GITHUB_REPO_URL   = os.environ.get("GITHUB_REPO_URL", "")  # ex: https://raw.githubusercontent.com/mgosnat/veille-ia/main

THEMES = {
    "agentique": {
        "label": "IA agentique",
        "color": "#16a34a",
        "keywords": [
            "agentic AI", "multi-agent", "AutoGen", "CrewAI", "LangGraph",
            "MCP protocol", "agent framework", "tool use", "autonomous agent",
            "AI workflow", "function calling", "open source agents", "reasoning model"
        ]
    },
    "gouvernance": {
        "label": "Gouvernance IA entreprise",
        "color": "#d97706",
        "keywords": [
            "AI governance", "EU AI Act", "ISO 42001", "responsible AI",
            "AI compliance", "AI policy", "algorithmic bias", "GPAI",
            "AI risk", "AI accountability", "AI regulation", "AI audit"
        ]
    }
}

# ─── Fetching insights via Claude API ────────────────────────────────────────

def fetch_insights(theme_id: str, theme: dict) -> list:
    """Appel Claude API avec web_search pour un thème donné."""
    print(f"  → Appel Claude API pour « {theme['label']} »...")

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1500,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{
            "role": "user",
            "content": (
                f"Tu es expert en veille stratégique IA. "
                f"Recherche les dernières actualités importantes (dernières 24-48h) sur : \"{theme['label']}\".\n"
                f"Mots-clés prioritaires : {', '.join(theme['keywords'])}.\n\n"
                "Réponds UNIQUEMENT avec un tableau JSON brut (sans markdown, sans backticks). "
                "4 objets avec exactement ces champs :\n"
                "- titre : string court et percutant\n"
                "- resume : 2-3 phrases en français\n"
                "- source : nom de la source\n"
                "- url : URL de l'article si disponible, sinon \"\"\n"
                "- pertinence : \"haute\" ou \"moyenne\"\n"
                "- categorie : ex \"Outil\", \"Recherche\", \"Réglementation\", \"Entreprise\", \"Communauté\"\n\n"
                "JSON brut uniquement."
            )
        }]
    }

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        },
        json=payload,
        timeout=90
    )
    resp.raise_for_status()
    data = resp.json()

    texts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    last_text = texts[-1] if texts else ""
    cleaned = last_text.replace("```json", "").replace("```", "").strip()
    match = re.search(r'\[[\s\S]*\]', cleaned)
    if match:
        return json.loads(match.group(0))
    print(f"    ⚠ Pas de JSON valide pour {theme_id}")
    return []

# ─── Email HTML ───────────────────────────────────────────────────────────────

def build_insight_card_html(item: dict, color: str) -> str:
    pertinence_bg  = "#dcfce7" if item.get("pertinence") == "haute" else "#fef9c3"
    pertinence_txt = "#15803d" if item.get("pertinence") == "haute" else "#854d0e"
    url = item.get("url", "")
    titre_html = (
        f'<a href="{url}" style="color:#111827;text-decoration:none;">{item.get("titre","")}</a>'
        if url else item.get("titre", "")
    )
    cat = item.get("categorie", "")
    return f"""
    <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
        <p style="margin:0;font-size:15px;font-weight:600;line-height:1.4;color:#111827;">{titre_html}</p>
        <span style="background:{pertinence_bg};color:{pertinence_txt};font-size:11px;padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{item.get("pertinence","")}</span>
      </div>
      <p style="margin:0 0 10px;font-size:13px;color:#4b5563;line-height:1.6;">{item.get("resume","")}</p>
      <div style="display:flex;gap:8px;align-items:center;">
        <span style="font-size:12px;color:#9ca3af;">{item.get("source","")}</span>
        {"<span style='background:#f3f4f6;color:#6b7280;font-size:11px;padding:1px 7px;border-radius:5px;'>" + cat + "</span>" if cat else ""}
      </div>
    </div>"""

def build_email_html(all_insights: dict, date_str: str) -> str:
    sections = ""
    for theme_id, insights in all_insights.items():
        theme = THEMES[theme_id]
        color = theme["color"]
        cards = "".join(build_insight_card_html(i, color) for i in insights)
        sections += f"""
        <div style="margin-bottom:36px;">
          <div style="margin-bottom:16px;">
            <span style="background:{color}1a;color:{color};font-size:13px;font-weight:600;padding:5px 14px;border-radius:20px;">{theme["label"]}</span>
          </div>
          {cards}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Veille IA – {date_str}</title></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:640px;margin:32px auto;background:#f9fafb;">
    <div style="background:#111827;border-radius:12px 12px 0 0;padding:24px 28px;">
      <p style="margin:0 0 4px;font-size:12px;color:#9ca3af;text-transform:uppercase;letter-spacing:0.08em;">Veille quotidienne</p>
      <h1 style="margin:0;font-size:22px;font-weight:700;color:#ffffff;">Tableau de veille IA</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#6b7280;">{date_str}</p>
    </div>
    <div style="background:#ffffff;border-radius:0 0 12px 12px;padding:28px;">
      {sections}
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
        Veille automatisée · ClinDiv · Généré par Claude AI + web search<br>
        <a href="{GITHUB_REPO_URL}" style="color:#9ca3af;">Voir le dashboard</a>
      </p>
    </div>
  </div>
</body>
</html>"""

# ─── Envoi SMTP ───────────────────────────────────────────────────────────────

def send_email(html: str, date_str: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 Veille IA – {date_str}"
    msg["From"]    = SMTP_USER
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"  ✅ Email envoyé à {EMAIL_TO}")

# ─── Sauvegarde JSON pour le dashboard ───────────────────────────────────────

def save_insights_json(all_insights: dict) -> None:
    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "date_fr": datetime.now().strftime("%d/%m/%Y"),
        "insights": all_insights
    }
    with open("data/insights.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("  ✅ data/insights.json sauvegardé")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    date_str = datetime.now().strftime("%A %d %B %Y").capitalize()
    print(f"\n🔍 Veille IA – {date_str}\n")

    all_insights = {}
   for i, (theme_id, theme) in enumerate(THEMES.items()):
        print(f"[{theme['label']}]")
        if i > 0:
            print("  → Pause 30s entre les appels API...")
            time.sleep(30)
        insights = fetch_insights(theme_id, theme)
        all_insights[theme_id] = insights
        print(f"  → {len(insights)} insights trouvés\n")

    save_insights_json(all_insights)

    print("[Email]")
    html = build_email_html(all_insights, date_str)
    send_email(html, date_str)

    print("\n✅ Pipeline terminé avec succès.")

if __name__ == "__main__":
    main()
