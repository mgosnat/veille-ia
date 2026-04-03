import os, json, re, smtplib, ssl, requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_PASS"]
EMAIL_TO  = os.environ["EMAIL_TO"]
SMTP_HOST = os.environ.get("SMTP_HOST", "ssl0.ovh.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))

def call_claude(prompt):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"Content-Type":"application/json","x-api-key":ANTHROPIC_API_KEY,"anthropic-version":"2023-06-01"},
        json={"model":"claude-sonnet-4-20250514","max_tokens":2000,
              "tools":[{"type":"web_search_20250305","name":"web_search"}],
              "messages":[{"role":"user","content":prompt}]},
        timeout=120
    )
    resp.raise_for_status()
    texts = [b["text"] for b in resp.json().get("content",[]) if b.get("type")=="text"]
    return texts[-1] if texts else ""

def fetch_all():
    prompt = (
        "Fais une veille des dernieres actualites IA (24-48h) sur deux themes.\n\n"
        "Theme 1 - IA agentique: agentic AI, multi-agent, AutoGen, CrewAI, LangGraph, MCP protocol, agent framework.\n"
        "Theme 2 - Gouvernance IA entreprise: AI governance, EU AI Act, ISO 42001, responsible AI, AI compliance, AI policy.\n\n"
        "Reponds UNIQUEMENT avec ce JSON brut (sans markdown):\n"
        '"agentique":[{"titre":"...","resume":"...","source":"...","url":"https://...","pertinence":"haute ou moyenne","categorie":"..."}],'
        '"gouvernance":[{"titre":"...","resume":"...","source":"...","url":"https://...","pertinence":"haute ou moyenne","categorie":"..."}]}\n\n'
        "4 items par theme. resume en francais 2-3 phrases. JSON brut uniquement."
    )
    txt = call_claude(prompt).replace("```json","").replace("```","").strip()
    m = re.search(r'\{[\s\S]*\}', txt)
    return json.loads(m.group(0)) if m else {"agentique":[],"gouvernance":[]}

def send_email(insights, date_str):
    colors = {"agentique":"#16a34a","gouvernance":"#d97706"}
    labels = {"agentique":"IA agentique","gouvernance":"Gouvernance IA entreprise"}
    sections = ""
    for tid, items in insights.items():
        c = colors[tid]
        cards = ""
        for item in items:
            pb = "#dcfce7" if item.get("pertinence")=="haute" else "#fef9c3"
            pt = "#15803d" if item.get("pertinence")=="haute" else "#854d0e"
            cards += f"""<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;">
<p style="margin:0 0 6px;font-size:15px;font-weight:600;color:#111827;">
{"<a href='"+item["url"]+"' style='color:#111827;'>"+item.get("titre","")+"</a>" if item.get("url") else item.get("titre","")}</p>
<p style="margin:0 0 10px;font-size:13px;color:#4b5563;">{item.get("resume","")}</p>
<div style="display:flex;gap:8px;">
<span style="font-size:12px;color:#9ca3af;">{item.get("source","")}</span>
<span style="background:{pb};color:{pt};font-size:11px;padding:2px 8px;border-radius:20px;">{item.get("pertinence","")}</span>
</div></div>"""
        sections += f'<div style="margin-bottom:32px;"><p style="font-weight:700;color:{c};">{labels[tid]}</p>{cards}</div>'
    html = f"""<html><body style="font-family:sans-serif;background:#f9fafb;padding:32px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;">
<h1 style="font-size:20px;margin:0 0 4px;">Veille IA</h1>
<p style="color:#6b7280;font-size:13px;margin:0 0 24px;">{date_str}</p>
{sections}
<p style="font-size:11px;color:#9ca3af;text-align:center;">Pipeline automatique ClinDiv</p>
</div></body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Veille IA - {date_str}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html,"html","utf-8"))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"Email envoye a {EMAIL_TO}")

def main():
    date_str = datetime.now().strftime("%d/%m/%Y")
    print("Veille IA -", date_str)
    print("Appel Claude API (un seul appel pour les deux themes)...")
    insights = fetch_all()
    print(f"agentique: {len(insights.get('agentique',[]))} items")
    print(f"gouvernance: {len(insights.get('gouvernance',[]))} items")
    os.makedirs("data", exist_ok=True)
    with open("data/insights.json","w",encoding="utf-8") as f:
        json.dump({"generated_at":datetime.utcnow().isoformat()+"Z","date_fr":date_str,"insights":insights},f,ensure_ascii=False,indent=2)
    print("insights.json sauvegarde")
    send_email(insights, date_str)
    print("Pipeline termine.")

if __name__ == "__main__":
    main()
