from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import anthropic
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

SCOPES = ['https://www.googleapis.com/auth/calendar']
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

def get_calendar_service():
    token_data = os.environ.get("GOOGLE_TOKEN_JSON")
    creds = Credentials.from_authorized_user_info(json.loads(token_data), SCOPES)
    if creds.expired and creds.refresh_token:
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

def create_event(summary, date_str, time_str=None):
    service = get_calendar_service()
    if time_str:
        start = {"dateTime": f"{date_str}T{time_str}:00", "timeZone": "Asia/Jerusalem"}
        end = {"dateTime": f"{date_str}T{time_str}:00", "timeZone": "Asia/Jerusalem"}
    else:
        start = {"date": date_str}
        end = {"date": date_str}
    event = {
        "summary": summary,
        "start": start,
        "end": end,
        "reminders": {"useDefault": True}
    }
    service.events().insert(calendarId="primary", body=event).execute()
    return f"✅ נוצר אירוע: {summary} בתאריך {date_str}"

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()
    msg = resp.message()
    try:
        events_text = get_events_this_week()
    except Exception as e:
        events_text = f"Could not load calendar: {e}"
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    result = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="""אתה עוזרת אישית חכמה בעברית. יש לך גישה ליומן Google Calendar של המשתמש.
אם המשתמש רוצה להוסיף אירוע או תזכורת, ענה בפורמט JSON בלבד ללא טקסט נוסף:
{"action": "create_event", "summary": "שם האירוע", "date": "YYYY-MM-DD", "time": "HH:MM"}
אחרת ענה בעברית רגילה, בתמציתיות.""",
        messages=[{"role": "user", "content": f"יומן השבוע:\n{events_text}\n\nהודעת המשתמש: {incoming_msg}"}]
    )
    response_text = result.content[0].text.strip()
    try:
        data = json.loads(response_text)
        if data.get("action") == "create_event":
            reply = create_event(data["summary"], data["date"], data.get("time"))
        else:
            reply = response_text
    except:
        reply = response_text
    msg.body(reply)
    return str(resp)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
