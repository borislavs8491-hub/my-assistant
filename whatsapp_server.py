from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import anthropic
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)

def get_events_this_week():
    service = get_calendar_service()
    now = datetime.utcnow()
    start_of_week = now - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=7)
    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_week.isoformat()+"Z",
        timeMax=end_of_week.isoformat()+"Z",
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    events = events_result.get("items", [])
    if not events:
        return "No events this week"
    return "\n".join([f"- {e.get('summary','No title')}: {e['start'].get('dateTime',e['start'].get('date'))}" for e in events])

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()
    msg = resp.message()
    
    events_text = get_events_this_week()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    result = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": f"You are a personal assistant. Calendar this week:\n{events_text}\n\nUser message: {incoming_msg}\n\nReply in Hebrew, be concise."}]
    )
    msg.body(result.content[0].text)
    return str(resp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
