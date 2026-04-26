"""
TRU Systems — Workflow Automation Audit Backend (Production)
----------------------------------------------------------
Flask server deployed on Render. Receives audit responses from
employees in any desk role, generates a personalized report using
Claude API, and emails it.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import smtplib
import os
import re
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
SENDER_EMAIL = os.environ.get("EMAIL_ADDRESS")
SENDER_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")

# ── CLAUDE PROMPT ────────────────────────────────────────────────────
SYSTEM_PROMPT = """You write personalized AI automation reports for TRU Systems. Your audience: any desk employee (sales, ops, marketing, admin, CS, EAs, managers) who wants to use AI to handle the repetitive parts of their job — not start a side hustle.

What we teach is called THE CONDUCTOR METHOD: you become the conductor of AI agents instead of doing every task by hand. Mention the framework by name once, naturally, in the intro.

Tone: warm, direct, like a sharp friend who actually builds these every day. No jargon, no lectures. Empathy first — confusion about AI is rational, not a personal failing.

Hard rules:
- Be specific to THEIR role, tools, and the routine task they described. Never generic.
- Don't tell them to quit their job and start a business. Frame everything as bringing AI INTO their existing job.
- Output valid JSON only. No markdown, no preamble, no code fences."""


def build_user_prompt(answers):
    return f"""Generate this person's personalized AI automation report.

Their answers:
- Role: {answers.get('q1', 'Not provided')}
- Tools they use daily: {answers.get('q2', 'Not provided')}
- A routine task they described: {answers.get('q3', 'Not provided')}
- How much of their day is repetitive: {answers.get('q4', 'Not provided')}
- Tasks they do by hand: {answers.get('q5', 'Not provided')}
- What matters most to them: {answers.get('q6', 'Not provided')}

Return JSON with this exact shape:
{{
  "intro": "3-4 sentences. Make them feel deeply understood. Reference their role, the tools they listed, and the task they described. Mention 'The Conductor Method' once, naturally, as what TRU Systems teaches. End with something like 'Here's what I'd change if I were in your seat.'",
  "opportunities": [
    {{
      "title": "Specific title naming the actual task and tools (e.g. 'Auto-build your weekly Slack pipeline report from CRM data'). Not generic.",
      "description": "5-7 sentences. (1) Name the specific problem in their workflow, referencing what THEY said. (2) Describe what the automation does step-by-step in plain language — what triggers it, what it does, what the end result looks like. (3) Tie to what they care about (q6).",
      "tool": "Specific tools and how they connect (e.g. 'Make.com connects your Sheets to Claude and Slack'). Pull from the tools they listed in q2.",
      "impact": "Specific and quantified (e.g. 'Saves 4-6 hours per week' or 'Report that took 90 min runs in 60 seconds')."
    }}
  ],
  "quick_win": "ONE specific action they can take in under 20 minutes RIGHT NOW that improves their process. Reference their actual role and tools. NOT a guilt trip about counting their problems — a real action that makes their day easier today.",
  "closing": "2-3 sentences tied to their q6 goal. End with: 'If you want to talk through which to build first, grab a free 15-min slot below.'",
  "permissions_note": "OPTIONAL — only include if their tools suggest enterprise/locked-down environment (Salesforce, Outlook, Teams + large company role). 1-2 sentences offering personal alternatives (ChatGPT/Claude in browser, personal accounts). Omit entirely for startup/small-team contexts. Don't force it."
}}

Generate exactly 3 opportunities. Each MUST reference their specific role, tools, OR the task they described. Never generic. Output JSON only."""


# ── GENERATE REPORT ──────────────────────────────────────────────────
def generate_report(answers):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": build_user_prompt(answers)}
        ]
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw)


# ── SEND EMAIL ───────────────────────────────────────────────────────
def send_report_email(email, name, report, answers):
    today = datetime.now().strftime("%B %d, %Y")
    subject = "Your Workflow Automation Audit — TRU Systems"

    opps_html = ""
    for i, opp in enumerate(report.get('opportunities', []), 1):
        opps_html += f"""
        <div style="background:#f9fafb; border-radius:10px; padding:20px;
        margin-bottom:14px; border-left:3px solid #c8102e;">
            <p style="font-size:11px; color:#c8102e; text-transform:uppercase;
            letter-spacing:0.06em; margin:0 0 6px; font-weight:600;">
            Opportunity {i}</p>
            <p style="font-size:17px; font-weight:600; color:#1a1a2e;
            margin:0 0 8px;">{opp.get('title', '')}</p>
            <p style="font-size:14px; color:#4b5563; line-height:1.6;
            margin:0 0 10px;">{opp.get('description', '')}</p>
            <p style="font-size:13px; color:#c8102e; margin:0 0 4px;">
            <strong>Tool:</strong> {opp.get('tool', '')}</p>
            <p style="font-size:13px; color:#4b5563; margin:0;">
            <strong>Impact:</strong> {opp.get('impact', '')}</p>
        </div>
        """

    permissions_note = report.get('permissions_note', '').strip() if report.get('permissions_note') else ''
    permissions_html = ""
    if permissions_note:
        permissions_html = f"""
        <div style="background:#f0f9ff; border-radius:10px; padding:18px;
        margin:20px 0; border: 1px solid #bae6fd;">
            <p style="font-size:11px; font-weight:600; color:#0369a1;
            text-transform:uppercase; letter-spacing:0.06em; margin:0 0 8px;">
            If your company locks things down</p>
            <p style="font-size:14px; color:#1a1a2e; line-height:1.6;
            margin:0;">{permissions_note}</p>
        </div>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px;
    margin: auto; padding: 20px; color: #1a1a2e;">

        <div style="border-bottom: 2px solid #c8102e; padding-bottom: 14px;
        margin-bottom: 28px;">
            <span style="font-size:22px; font-weight:700;
            color:#c8102e;">TRU</span><span style="font-size:22px;
            font-weight:600; color:#1a1a2e;">Systems</span>
            <h1 style="font-size:20px; font-weight:600; margin:8px 0 0;
            color:#1a1a2e;">Your Workflow Automation Audit</h1>
            <p style="font-size:13px; color:#6b7280; margin:4px 0 0;">
            {today} — {answers.get('q1', '')} using {answers.get('q2', '')}</p>
        </div>

        <p style="font-size:15px; line-height:1.7; color:#374151;">
        Hi {name},</p>
        <p style="font-size:15px; line-height:1.7; color:#374151;">
        {report.get('intro', '')}</p>

        <h2 style="font-size:16px; font-weight:600; color:#1a1a2e;
        margin:28px 0 14px;">Your top automation opportunities</h2>
        {opps_html}

        <div style="background:#fef2f2; border-radius:10px; padding:20px;
        margin:28px 0; border: 1px solid #fecaca;">
            <p style="font-size:11px; font-weight:600; color:#c8102e;
            text-transform:uppercase; letter-spacing:0.06em; margin:0 0 8px;">
            Your quick win for today</p>
            <p style="font-size:14px; color:#1a1a2e; line-height:1.6;
            margin:0;">{report.get('quick_win', '')}</p>
        </div>

        {permissions_html}

        <p style="font-size:15px; line-height:1.7; color:#374151;">
        {report.get('closing', '')}</p>

        <div style="background:#f9fafb; border-radius:10px; padding:24px;
        margin:28px 0; text-align:center; border: 1px solid #e5e7eb;">
            <p style="font-size:17px; font-weight:600; color:#1a1a2e;
            margin:0 0 8px;">Want help actually building this?</p>
            <p style="font-size:14px; color:#6b7280; margin:0 0 16px;
            line-height:1.5;">Book a free 15-minute call with the team.
            We'll walk through your results together, pick the best
            opportunity for your job, and show you exactly how to
            build it. Just 15 minutes — and you'll leave with a
            clear next step.</p>
            <a href="https://calendly.com/gettrusystems/30min" style="display:inline-block;
            padding:14px 32px; background:#c8102e; color:white;
            text-decoration:none; border-radius:8px; font-size:15px;
            font-weight:600;">Book your free 15-min call</a>
            <p style="font-size:13px; color:#6b7280; margin:10px 0 0;">
            100% free. 15 minutes. No catch.</p>
        </div>

        <p style="font-size:12px; color:#9ca3af; text-align:center;
        margin-top:28px;">
        TRU Systems — gettrusystems@gmail.com</p>
    </body>
    </html>
    """

    plain = f"""
Your Workflow Automation Audit — TRU Systems
{today}

Hi {name},

{report.get('intro', '')}

YOUR TOP AUTOMATION OPPORTUNITIES:
{''.join([f"{i+1}. {opp.get('title', '')}" + chr(10) + f"{opp.get('description', '')}" + chr(10) + f"Tool: {opp.get('tool', '')}" + chr(10) + f"Impact: {opp.get('impact', '')}" + chr(10) + chr(10) for i, opp in enumerate(report.get('opportunities', []))])}

YOUR QUICK WIN FOR TODAY:
{report.get('quick_win', '')}
{(chr(10) + chr(10) + 'IF YOUR COMPANY LOCKS THINGS DOWN:' + chr(10) + permissions_note) if permissions_note else ''}

{report.get('closing', '')}

Want help actually building this? Book a free 15-minute call with
the team. We'll walk through your results, pick the best opportunity
for your job, and show you exactly how to build it. Just 15
minutes — and you'll leave with a clear next step.

Book your free call: https://calendly.com/gettrusystems/30min

Prefer email? gettrusystems@gmail.com

— TRU Systems
""".strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = email
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, email, msg.as_string())


# ── ROUTES ───────────────────────────────────────────────────────────
@app.route('/generate-report', methods=['POST'])
def generate_report_route():
    try:
        data = request.json
        answers = data.get('answers', {})
        email = answers.get('email', '')
        name = answers.get('name', 'there')

        report = generate_report(answers)
        send_report_email(email, name, report, answers)

        return jsonify({
            "success": True,
            "report": report
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"})


# ── MAIN ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
