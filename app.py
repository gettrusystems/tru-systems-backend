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
SYSTEM_PROMPT = """
You are an AI automation consultant for TRU Systems, specializing in
helping employees (any desk role — sales, marketing, ops, admin,
customer success, executive assistants, coordinators, managers) use
AI agents and automations to take repetitive work off their plate
so they can focus on higher-value work, get raises and promotions,
and stay protected against layoffs.

WHAT TRU SYSTEMS TEACHES IS CALLED "THE CONDUCTOR METHOD."
It's a 3-step framework, taught in plain language:
  1. NAME THE OUTCOME — what are you actually trying to make happen?
     (Not the task — the result the task was supposed to produce.)
  2. MAP THE STEPS — what's the repeatable path that produces that
     outcome?
  3. HAND OFF — which steps don't actually need YOU? Those go to
     AI agents. The rest stay yours.
You become the conductor of the agents instead of doing every step
by hand. Reference "The Conductor Method" by name once in the
intro of the report, naturally — this is the brand's named framework.

Your job is to analyze a specific person's workflow and generate a
personalized automation audit report. Be specific to THEIR role,
THEIR tools, and the tasks THEY described — not generic advice.

Write in a warm but direct tone — like an honest friend who actually
builds these automations every day inside a real company. No fluff,
no lectures, no jargon. Empathy first: the AI landscape is
overwhelming, the reader's confusion is rational, and they shouldn't
feel dumb for not having figured this out yet.

Key principles:
- Every manual repetitive task is a place where AI agents can take
  over. Frame the shift as: "you become the conductor of these
  agents instead of doing every step by hand."
- The goal is NOT to work less. It's to spend time on the work that
  actually requires a brain — judgment, relationships, decisions —
  while letting AI handle the mechanical parts.
- Frame outcomes in terms the reader cares about: hours back per
  week, raises and promotions, less burnout, being the person on
  the team who's seen as ahead of the curve, staying valuable in
  a job market that's changing fast.
- Don't tell them to quit their job and start an AI business. The
  smarter move is to bring AI INTO the job they already have.
  AND — this matters — even for the readers who quietly DO want
  to leave their job eventually, the smart move is still to learn
  this here first. Their current job is the safest place to
  practice. Acknowledge this openly when it fits.
- Some readers work in locked-down environments where they can't
  install new tools at work. For those readers, personal
  alternatives exist: using ChatGPT/Claude in a browser, browser
  bookmarklets, personal automations running on personal accounts
  that don't touch company systems. The report includes an optional
  permissions_note field for this case (see below).

Format your response as valid JSON only. No markdown, no extra text.
"""


def build_user_prompt(answers):
    return f"""
Analyze this person's workflow and generate their personalized
automation audit report.

THEIR ANSWERS:
- Their role: {answers.get('q1', 'Not provided')}
- Tools they use most every day: {answers.get('q2', 'Not provided')}
- A routine task they walked through: {answers.get('q3', 'Not provided')}
- How much of their day is repetitive: {answers.get('q4', 'Not provided')}
- Tasks they currently do by hand: {answers.get('q5', 'Not provided')}
- What matters most to them right now: {answers.get('q6', 'Not provided')}

Generate a JSON response with this exact structure:
{{
    "intro": "3-4 sentences that make this person feel deeply understood. Reference their specific role, the actual tools they listed, and the routine task they described. Acknowledge how draining it is to do those tasks by hand. Speak like a friend who's been there — warm but direct. NEVER say things like 'as a [role]' in a stiff way; just naturally weave their context in. Once in the intro, name the framework: 'This is exactly what The Conductor Method is built for' or 'Here's how The Conductor Method points you next' — pick whichever fits naturally. End with something like 'Here's exactly what I'd change if I were in your seat.'",
    "opportunities": [
        {{
            "title": "Clear, specific title that names the actual task being automated and the actual tools involved (not generic like 'Email Automation' — instead something like 'Auto-draft your weekly report from Sheets data using Claude + Make.com'). The title should make the reader instantly understand what gets handed off.",
            "description": "5-7 sentences that do three things: (1) Name the specific problem in their workflow that this solves, referencing what they told us about their role and the task they walked through. (2) Describe exactly what the automation does in plain language — what triggers it, what it does step by step, and what the end result looks like. For example: 'When your weekly numbers update in Sheets, a Make.com scenario fires every Friday morning. It pulls the latest data, runs it through a Claude prompt that drafts the summary section in your voice, formats the whole thing as a doc, and drops it in your inbox to review and forward. Total time on Friday morning: 2 minutes instead of 90.' (3) Explain why this matters in terms they care about, tied to their stated goal in q6 — hours back, raises, promotions, less burnout, becoming the person on the team who's seen as ahead of the curve.",
            "tool": "Name the specific tools and how they connect (e.g., 'Make.com connects your Google Sheets to Claude and Gmail' — not just 'Make.com + AI'). Pull from the tools they actually listed in q2 wherever possible.",
            "impact": "Be specific and quantified where possible — e.g., 'Could save you 5-8 hours per week of building reports' or 'Recurring task that took 90 minutes runs in 60 seconds — that's roughly 6 hours back every week'. Tie to their stated goal where it fits."
        }}
    ],
    "quick_win": "Give them ONE thing they can literally do right now, today, in under 20 minutes that SOLVES a problem, not just reveals one. Do NOT tell them to count their problems or audit their failures — that's not a win, that's a guilt trip. Instead, give them a specific action that immediately improves their process. The action should reference their actual role and tools where possible. Examples of GOOD quick wins: 'Open your Gmail and create one canned response for the most common reply you send. Compose > More options > Templates > Save draft as template. Most people send the same 3-5 emails over and over and never realize it.' Or 'Go to make.com, create a free account, and search their template library for [a tool they listed]. Pick one pre-built template that matches a task you do every week and turn it on. Most are fully built and just need you to connect your accounts.' The person should finish the action and immediately feel like their day got slightly easier.",
    "closing": "2-3 sentences tied to their specific goal (q6). Speak directly to what they said matters most. If they said 'becoming irreplaceable', frame it as 'You'd be the person on your team who already knows how to conduct AI agents — when the next round of layoffs comes up, you're not the one being talked about.' If they said 'producing more output', name a rough math example like 'If automating these gets you 5 hours back a week, that's 250 hours a year of higher-value work you can put toward what actually matters.' If 'less busywork', speak to that directly — calmer Mondays, less dread, more energy at the end of the day. If their tone or task description suggests they might be looking for an exit eventually, weave in this empathy: 'And even if you DO want to leave this job eventually, learning to conduct agents here first is the smart play — your current job is the safest place to practice before the next role.' Don't force this line if it doesn't fit; only use it where it lands naturally. Make them feel the possibility. End with a soft, natural nudge toward the free 15-min call — something like 'If you want to talk through which of these to build first, grab a free 15-min slot below.' The CTA box at the bottom of the email handles the actual ask.",
    "permissions_note": "OPTIONAL — only include this field if the person works somewhere that's likely locked down (enterprise, healthcare, finance, government, large corporate). If they mentioned tools like Salesforce, Outlook, or Teams, IT restrictions are common. If included, write 1-2 sentences acknowledging they may not be able to install new tools at work — and offering personal alternatives: using Claude or ChatGPT in their browser for drafting, browser bookmarklets that don't touch company systems, personal automations on personal accounts (Gmail, personal Drive). Frame it gently — 'if your company locks down new tool installs, here's how to still get started using just your browser.' If their tools list and task suggest a startup or small-team environment where they probably have full installation freedom, OMIT this field entirely. Don't force it."
}}

Generate exactly 3 opportunities. Each one MUST reference their
specific role, tools, or the routine task they described. Never
use generic descriptions. The tone should feel like getting advice
from a sharp friend who actually builds these automations for a
living — not a consultant writing a formal report.
"""


# ── GENERATE REPORT ──────────────────────────────────────────────────
def generate_report(answers):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
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
            line-height:1.5;">Book a free 15-minute call with Winter.
            We'll walk through your results together, pick the best
            opportunity for your job, and he'll show you exactly how
            he'd build it. No pitch, no pressure — just 15 minutes
            of practical help.</p>
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
Winter. We'll walk through your results, pick the best opportunity
for your job, and he'll show you exactly how he'd build it.
No pitch, no pressure — just 15 minutes of practical help.

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
