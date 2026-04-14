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


def filter_recent(items, max_days=14):
    """Remove items older than max_days. Keep items with no date (Claude couldn't verify)."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=max_days)
    kept = []
    for item in items:
        date_str = item.get("date_publication", "").strip()
        if not date_str:
            # No date — keep but flag
            item["date_publication"] = ""
            kept.append(item)
            continue
        try:
            # Parse JJ/MM/AAAA
            d = datetime.strptime(date_str, "%d/%m/%Y")
            if d >= cutoff:
                kept.append(item)
            else:
                print(f"  Filtre anciennete: article exclu ({date_str}) - {item.get('titre','')[:60]}")
        except ValueError:
            # Unparseable date — keep it
            kept.append(item)
    return kept

COLORS = {
    "agentique":  "#16a34a",
    "gouvernance":"#d97706",
    "clinique":   "#0ea5e9"
}
LABELS = {
    "agentique":  "IA agentique",
    "gouvernance":"Gouvernance IA entreprise",
    "clinique":   "Diversite & essais cliniques"
}

def call_claude(prompt, max_retries=5, wait_seconds=60):
    import time
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4000,
                    "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=120
            )
            resp.raise_for_status()
            texts = [b["text"] for b in resp.json().get("content", []) if b.get("type") == "text"]
            return texts[-1] if texts else ""
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status in (429, 529) and attempt < max_retries:
                print(f"API surchargee (erreur {status}), tentative {attempt}/{max_retries}, attente {wait_seconds}s...")
                time.sleep(wait_seconds * attempt)  # attente progressive
                time.sleep(wait_seconds)
            else:
                raise
    return ""

def fetch_all():
    today = datetime.utcnow().strftime("%d %B %Y")
    prompt = (
        f"Nous sommes le {today}. "
        "Fais une veille des actualites publiees dans les 14 DERNIERS JOURS MAXIMUM sur trois themes.\n\n"
        "REGLE STRICTE : n'inclure un article que si tu peux verifier qu'il a ete publie dans les 14 derniers jours. "
        "Si la date de publication n'est pas clairement identifiable ou si l'article est plus ancien, NE PAS l'inclure. "
        "Mieux vaut avoir 3-4 articles recents et verifies que 8 articles dont certains sont anciens.\n\n"

        "Theme 1 - IA agentique (focus TERRAIN et PRATIQUE uniquement):\n"
        "Cherche EXCLUSIVEMENT : (a) nouveaux outils ou frameworks agents sortis ces 2 semaines avec lien GitHub ou page produit, "
        "(b) retours d'experience concrets de professionnels qui ont deploye des agents en production (pas de theorie), "
        "(c) tutoriels pratiques step-by-step sur AutoGen / CrewAI / LangGraph / MCP / n8n agents, "
        "(d) annonces de produits agentiques avec demo ou benchmark reel, "
        "(e) cas d'usage metiers documentes (workflow automatise, agent RH, agent support, etc.).\n"
        "EXCLURE : articles conceptuels sur 'ce que sont les agents', predictions, opinions generales, articles de blog sans implementation concrete.\n\n"

        "Theme 2 - Gouvernance IA entreprise: AI governance, EU AI Act implementation, ISO 42001, responsible AI deployment, "
        "AI compliance frameworks, enterprise AI policy, AI Act enforcement updates.\n\n"

        "Theme 3 - Diversite en essais cliniques: clinical trial diversity, health equity, underrepresented populations, "
        "minority recruitment, FDA diversity action plan, algorithmic bias clinical, inclusive trial design.\n\n"

        "IMPORTANT : le champ pertinence doit contenir UNIQUEMENT le mot \"haute\" ou le mot \"moyenne\". Rien d'autre. Pas de chiffre, pas de Tres elevee, pas de elevee, pas de score. Uniquement \"haute\" ou \"moyenne\".\n\n"
        "Reponds UNIQUEMENT avec ce JSON brut (sans markdown):\n"
        '{"agentique":[{"titre":"...","resume":"...","source":"...","url":"https://...","date_publication":"JJ/MM/AAAA ou vide si inconnue","pertinence":"haute","categorie":"outil"}],'
        '"gouvernance":[{"titre":"...","resume":"...","source":"...","url":"https://...","date_publication":"JJ/MM/AAAA ou vide si inconnue","pertinence":"haute","categorie":"..."}],'
        '"clinique":[{"titre":"...","resume":"...","source":"...","url":"https://...","date_publication":"JJ/MM/AAAA ou vide si inconnue","pertinence":"haute","categorie":"..."}]}\n\n'
        "Maximum 8 items par theme, minimum 0 si rien de recent. resume en francais 2-3 phrases. JSON brut uniquement."
    )
    txt = call_claude(prompt).replace("```json", "").replace("```", "").strip()
    m = re.search(r'\{[\s\S]*\}', txt)
    if not m:
        return {"agentique": [], "gouvernance": [], "clinique": []}
    data = json.loads(m.group(0))
    for theme in ["agentique", "gouvernance", "clinique"]:
        before = len(data.get(theme, []))
        data[theme] = filter_recent(data.get(theme, []))
        after = len(data[theme])
        if before != after:
            print(f"  {theme}: {before - after} article(s) trop ancien(s) retire(s)")
    return data

def make_card(item, color):
    pb = "#dcfce7" if item.get("pertinence") == "haute" else "#fef9c3"
    pt = "#15803d" if item.get("pertinence") == "haute" else "#854d0e"
    url = item.get("url", "")
    titre = (
        f'<a href="{url}" style="color:#111827;text-decoration:none;">{item.get("titre","")}</a>'
        if url else item.get("titre", "")
    )
    cat = item.get("categorie", "")
    date_pub = item.get("date_publication", "")
    return (
        f'<div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:12px;">'
        f'<p style="margin:0 0 6px;font-size:15px;font-weight:600;color:#111827;">{titre}</p>'
        f'<p style="margin:0 0 10px;font-size:13px;color:#4b5563;line-height:1.6;">{item.get("resume","")}</p>'
        f'<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">'
        f'<span style="font-size:12px;color:#9ca3af;">{item.get("source","")}</span>'
        + (f'<span style="font-size:11px;color:#d1d5db;">· {date_pub}</span>' if date_pub else '')
        + f'<span style="background:{pb};color:{pt};font-size:11px;padding:2px 8px;border-radius:20px;">{item.get("pertinence","")}</span>'
        + (f'<span style="background:#f3f4f6;color:#6b7280;font-size:11px;padding:1px 7px;border-radius:5px;">{cat}</span>' if cat else '')
        + '</div></div>'
    )

def send_email(insights, date_str):
    total = sum(len(insights.get(tid, [])) for tid in ["agentique", "gouvernance", "clinique"])
    sections = ""
    for tid in ["agentique", "gouvernance", "clinique"]:
        items = insights.get(tid, [])
        if not items:
            c = COLORS[tid]
            sections += (
                f'<div style="margin-bottom:32px;">'
                f'<p style="font-weight:700;color:{c};font-size:15px;margin:0 0 12px;">{LABELS[tid]}</p>'
                f'<p style="color:#9ca3af;font-size:13px;font-style:italic;">Aucun article recent verifiable sur ce theme cette semaine.</p>'
                f'</div>'
            )
            continue
        c = COLORS[tid]
        cards = "".join(make_card(item, c) for item in items)
        sections += (
            f'<div style="margin-bottom:32px;">'
            f'<p style="font-weight:700;color:{c};font-size:15px;margin:0 0 12px;">'
            f'{LABELS[tid]} <span style="font-weight:400;font-size:13px;color:#9ca3af;">({len(items)} articles)</span></p>'
            f'{cards}</div>'
        )
    html = (
        f'<html><body style="font-family:sans-serif;background:#f9fafb;padding:32px;">'
        f'<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:28px;">'
        f'<h1 style="font-size:20px;margin:0 0 4px;">Veille IA</h1>'
        f'<p style="color:#6b7280;font-size:13px;margin:0 0 4px;">{date_str}</p>'
        f'<p style="color:#9ca3af;font-size:12px;margin:0 0 24px;">Articles des 14 derniers jours uniquement · {total} articles verifies</p>'
        f'{sections}'
        f'<p style="font-size:11px;color:#9ca3af;text-align:center;">Pipeline automatique ClinDiv</p>'
        f'</div></body></html>'
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Veille IA - {date_str}"
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context()) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"Email envoye a {EMAIL_TO}")

def main():
    date_str = datetime.now().strftime("%d/%m/%Y")
    print("Veille IA -", date_str)
    print("Appel Claude API (3 themes en un seul appel)...")
    insights = fetch_all()
    for tid in ["agentique", "gouvernance", "clinique"]:
        print(f"{tid}: {len(insights.get(tid, []))} items")
    os.makedirs("data", exist_ok=True)
    with open("data/insights.json", "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "date_fr": date_str,
            "insights": insights
        }, f, ensure_ascii=False, indent=2)
    print("insights.json sauvegarde")
    send_email(insights, date_str)
    print("Pipeline termine.")

if __name__ == "__main__":
    main()
