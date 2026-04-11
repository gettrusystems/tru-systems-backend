"""
TRU Systems — Sales Automation Audit Backend (Production)
----------------------------------------------------------
Flask server deployed on Render. Receives audit responses from salespeople,
generates a personalized report using Claude API, and emails it.
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
SYSTEM_PROMPT = """
You are an AI automation consultant for TRU Systems, specializing in
helping salespeople use AI and automation to close more deals and earn
more commission.

Your job is to analyze a salesperson's specific workflow and generate
a personalized automation audit report. Be specific to their role,
their CRM, their pipeline, and their pain points.

Write in a warm but direct tone — like an honest friend who actually
sells for a living and tells it straight. No fluff, no generic advice.
Every recommendation must feel custom to this specific salesperson's
situation.

Key principles:
- Speed-to-lead is about REVENUE, not just time savings. Faster
  response = higher close rate = more commission.
- Every manual step in their pipeline is a leak where deals slip through.
- The goal isn't to work less — it's to sell more by eliminating the
  admin that eats into selling time.
- Frame everything in terms of deals, commission, and career impact.

Format your response as valid JSON only. No markdown, no extra text.
"""


def build_user_prompt(answers):
    return f"""
Analyze this salesperson's workflow and generate their personalized
automation audit report.

THEIR DETAILS:
- Sales role: {answers.get('q1', 'Not provided')}
- CRM they use: {answers.get('q2', 'Not provided')}
- Compensation structure: {answers.get('q3', 'Not provided')}
- Their lead-to-close process (manual steps): {answers.get('q4', 'Not provided')}
- Current lead response time: {answers.get('q5', 'Not provided')}
- Biggest time drain outside of selling: {answers.get('q6', 'Not provided')}
- What matters most to them: {answers.get('q7', 'Not provided')}

Generate a JSON response with this exact structure:
{{
    "intro": "2-3 sentences personally addressing their situation. Reference their specific role, CRM, and pain points. Make them feel understood as a salesperson. Speak in terms of deals, pipeline, and commission.",
    "opportunities": [
        {{
            "title": "Short title for this automation opportunity",
            "description": "3-4 sentences explaining this specific opportunity for their sales role. Reference their actual CRM and process. Be concrete about what gets automated and how.",
            "tool": "The specific tool or combination recommended (e.g., Make.com + Salesforce, HubSpot sequences, Zapier + Slack)",
            "impact": "One sentence on the direct outcome — framed as deals closed, commission earned, or time reclaimed for selling"
        }}
    ],
    "quick_win": "One specific thing they can do TODAY in under 30 minutes that will immediately improve their sales process. Be very specific — name the tool, the action, and the outcome.",
    "closing": "2 sentences of encouragement tied to their specific goal. If they want more commission, speak to that. If they want job security, speak to that. Make it personal."
}}

Generate exactly 3-4 opportunities. Make every recommendation specific to
their CRM and sales process. Never be generic.
"""


# ── GENERATE REPORT ──────────────────────────────────────────────────
def generate_report(answers):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
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
    subject = "Your Sales Automation Audit — TRU Systems"

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
            color:#1a1a2e;">Your Sales Automation Audit</h1>
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

        <p style="font-size:15px; line-height:1.7; color:#374151;">
        {report.get('closing', '')}</p>

        <div style="background:#f9fafb; border-radius:10px; padding:24px;
        margin:28px 0; text-align:center; border: 1px solid #e5e7eb;">
            <p style="font-size:17px; font-weight:600; color:#1a1a2e;
            margin:0 0 8px;">Want help implementing this?</p>
            <p style="font-size:14px; color:#6b7280; margin:0 0 16px;
            line-height:1.5;">Join the TRU Systems community — get direct
            access to me, ask your automation questions anytime, and book
            1-on-1 sessions when you're ready to build.</p>
            <a href="[COMMUNITY_PLATFORM_URL]" style="display:inline-block;
            padding:14px 32px; background:#c8102e; color:white;
            text-decoration:none; border-radius:8px; font-size:15px;
            font-weight:600;">Join the community — $29/month</a>
            <p style="font-size:12px; color:#6b7280; margin:12px 0 0;">
            Or <a href="https://calendly.com/gettrusystems/30min"
            style="color:#c8102e;">book a 1-on-1 session</a> for
            hands-on implementation help.</p>
        </div>

        <p style="font-size:12px; color:#9ca3af; text-align:center;
        margin-top:28px;">
        TRU Systems — gettrusystems@gmail.com</p>
    </body>
    </html>
    """

    plain = f"""
Your Sales Automation Audit — TRU Systems
{today}

Hi {name},

{report.get('intro', '')}

YOUR TOP AUTOMATION OPPORTUNITIES:
{''.join([f"{i+1}. {opp.get('title', '')}" + chr(10) + f"{opp.get('description', '')}" + chr(10) + f"Tool: {opp.get('tool', '')}" + chr(10) + f"Impact: {opp.get('impact', '')}" + chr(10) + chr(10) for i, opp in enumerate(report.get('opportunities', []))])}

YOUR QUICK WIN FOR TODAY:
{report.get('quick_win', '')}

{report.get('closing', '')}

Ready to implement? Join the TRU Systems community:
[COMMUNITY_PLATFORM_URL]

Or book a 1-on-1 session: https://calendly.com/gettrusystems/30min

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
