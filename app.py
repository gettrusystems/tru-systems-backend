"""
TRU Systems — Workflow Automation Audit Backend (Production)
----------------------------------------------------------
Flask server deployed on Render. Receives audit responses from
employees in any desk role and generates a personalized report
using the Claude API. Returns the report as JSON to the frontend.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import re
import json

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# ── CLAUDE PROMPT ────────────────────────────────────────────────────
SYSTEM_PROMPT = """You write personalized AI automation reports for TRU Systems. Your audience: any desk employee (sales, ops, marketing, admin, CS, EAs, managers) who wants to use AI to handle the repetitive parts of their job — not start a side hustle.

What we teach is called THE CONDUCTOR METHOD: you become the conductor of AI agents instead of doing every task by hand. Mention the framework by name once, naturally, in the intro.

Tone: warm, direct, like a sharp friend who actually builds these every day. No jargon, no lectures. Empathy first — confusion about AI is rational, not a personal failing.

Hard rules:
- Be specific to THEIR role, tools, and the routine task they described. Never generic.
- NEVER invent specific brand names the user didn't mention. If they said "CRM" without naming one, say "your CRM" — don't write "Salesforce" or "HubSpot." If they said "email" without naming Gmail/Outlook, say "your inbox." If they listed multiple options like "Gmail / Outlook," pick a phrasing that works for both ("your inbox") rather than choosing one. Same for project trackers, scheduling tools, etc. Specificity is only good when it's THEIR specificity.
- When their answer is generic (e.g. just "CRM" or "scheduling tool"), match that level of generality in your output. Their report should reflect what THEY told you, not what you assume about their stack.
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
      "description": "5-7 sentences. (1) Name the specific problem in their workflow, referencing what THEY said — using their wording for tools (don't substitute 'Salesforce' if they said 'CRM'). (2) Describe what the automation does step-by-step in plain language — what triggers it, what it does, what the end result looks like. (3) Tie to what they care about (q6).",
      "tool": "Specific tools and how they connect (e.g. 'Make.com connects your Sheets to Claude and Slack'). ONLY name brands the user explicitly listed in q2. If they said 'CRM' generically, write 'your CRM' — don't pick Salesforce or HubSpot. If they listed 'Gmail / Outlook,' write 'your inbox.' Never fill in blanks they left.",
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



# ── ROUTES ───────────────────────────────────────────────────────────
@app.route('/generate-report', methods=['POST'])
def generate_report_route():
    try:
        data = request.json
        answers = data.get('answers', {})
        report = generate_report(answers)
        return jsonify({
            "success": True,
            "report": report
        })
    except Exception as e:
        print(f"Error generating report: {e}")
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
