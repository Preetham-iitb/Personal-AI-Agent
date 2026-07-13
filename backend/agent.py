import os
import json
import asyncio
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from langchain_groq import ChatGroq
# pyrefly: ignore [missing-import]
from langchain_core.tools import tool
# pyrefly: ignore [missing-import]
from langchain_core.messages import ToolMessage
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright
import base64
from email.mime.text import MIMEText

# pyrefly: ignore [missing-import]
from google.auth.transport.requests import Request
# pyrefly: ignore [missing-import]
from google.oauth2.credentials import Credentials
# pyrefly: ignore [missing-import]
from google_auth_oauthlib.flow import InstalledAppFlow
# pyrefly: ignore [missing-import]
from googleapiclient.discovery import build
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

p = None
browser = None
page = None
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_DIR = os.path.join(os.path.dirname(__file__), "credentials")
GMAIL_CLIENT_SECRET_PATH = os.path.join(GMAIL_DIR, "client_secret.json")
GMAIL_TOKEN_PATH = os.path.join(GMAIL_DIR, "token.json")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "food_delivery")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
CUSTOMERS_TABLE = os.getenv("CUSTOMERS_TABLE", "customers")

# We use global state for the send_update callback to easily access it in tools for the demo
_send_update = None


def get_gmail_credentials():
    creds = None

    if os.path.exists(GMAIL_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if _send_update:
                _send_update("Opening Gmail consent screen...")
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        os.makedirs(GMAIL_DIR, exist_ok=True)
        with open(GMAIL_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def load_profile_email():
    profile_path = os.path.join(os.path.dirname(__file__), "profile.json")
    with open(profile_path, "r") as f:
        profile = json.load(f)

    from_email = profile.get("email")
    if not from_email:
        raise ValueError("No sender email found in profile.json")

    return from_email


def fetch_customers(user_id=None, subscription_active=None, email_not_null=False, delivery_zone=None):
    where_clauses = []
    params = []

    if user_id is not None:
        where_clauses.append("user_id = %s")
        params.append(user_id)

    if subscription_active is not None:
        where_clauses.append("subscription_active = %s")
        params.append(subscription_active)

    if email_not_null:
        where_clauses.append("email IS NOT NULL AND email <> ''")

    if delivery_zone is not None and str(delivery_zone).strip() != "":
        where_clauses.append("delivery_zone = %s")
        params.append(str(delivery_zone).strip())

    query = f"SELECT user_id, signup_date, delivery_zone, subscription_active, email FROM {CUSTOMERS_TABLE}"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " ORDER BY user_id"

    connection = get_db_connection()
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    finally:
        connection.close()


def send_gmail_message(to_email: str, subject: str, body: str) -> None:
    from_email = load_profile_email()

    if not os.path.exists(GMAIL_CLIENT_SECRET_PATH):
        raise FileNotFoundError(f"Missing Gmail client secret file at {GMAIL_CLIENT_SECRET_PATH}")

    creds = get_gmail_credentials()
    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(body)
    message["to"] = to_email
    message["from"] = from_email
    message["subject"] = subject

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service.users().messages().send(userId="me", body={"raw": raw_message}).execute()

def init_browser():
    global p, browser, page
    if p is None:
        if _send_update:
            _send_update("Starting Playwright Browser...")
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False, slow_mo=500, channel="msedge")
        context = browser.new_context()
        page = context.new_page()

@tool
def get_my_profile() -> str:
    """Get the user's profile details from profile.json. Call this to know what data you are filling forms for."""
    if _send_update:
        _send_update("Reading profile.json...")
    try:
        # Resolve path relative to this script
        profile_path = os.path.join(os.path.dirname(__file__), "profile.json")
        with open(profile_path, "r") as f:
            data = json.load(f)
        return json.dumps(data)
    except Exception as e:
        return f"Error reading profile.json: {e}"


@tool
def find_customers(
    user_id: int | None = None,
    subscription_active: bool | None = None,
    email_not_null: bool = False,
    delivery_zone: str | None = None,
) -> str:
    """Find customers in the database using safe filter fields."""
    try:
        rows = fetch_customers(
            user_id=user_id,
            subscription_active=subscription_active,
            email_not_null=email_not_null,
            delivery_zone=delivery_zone,
        )
        if not rows:
            return "No matching customers found."
        return json.dumps(rows, default=str)
    except Exception as e:
        return f"Error finding customers: {e}"

@tool
def navigate_to(url: str) -> str:
    """Navigate the browser to the specified URL."""
    init_browser()
    if _send_update:
        _send_update(f"Navigating to {url}")
    try:
        page.goto(url, timeout=15000)
        return f"Successfully navigated to {url}. Page title is '{page.title()}'"
    except Exception as e:
        return f"Error navigating to {url}: {e}"

@tool
def click_element(selector: str) -> str:
    """Click an element on the page matching the given CSS selector."""
    init_browser()
    if _send_update:
        _send_update(f"Clicking element: {selector}")
    try:
        page.locator(selector).first.click(timeout=5000, force=True)
        return f"Successfully clicked element: {selector}"
    except Exception as e:
        return f"Error clicking element {selector}: {e}"

@tool
def type_text(selector: str, text: str) -> str:
    """Type text into an element matching the given CSS selector."""
    init_browser()
    if _send_update:
        _send_update(f"Typing '{text}' into {selector}")
    try:
        page.locator(selector).first.fill(text, timeout=5000, force=True)
        return f"Successfully typed text into element: {selector}"
    except Exception as e:
        try:
            page.locator(selector).first.click(timeout=3000, force=True)
            page.keyboard.type(text)
            return f"Successfully typed text into element: {selector} (using keyboard fallback)"
        except Exception as e2:
            return f"Error typing into element {selector}: {e2}"

@tool
def fill_demoqa_form() -> str:
    """Fill the DemoQA practice form using values from profile.json."""
    init_browser()
    try:
        profile_path = os.path.join(os.path.dirname(__file__), "profile.json")
        with open(profile_path, "r") as f:
            data = json.load(f)

        first_name = data.get("firstName", "")
        last_name = data.get("lastName", "")
        email = data.get("email", "")
        gender = data.get("gender", "")
        mobile = data.get("mobile", "")

        page.goto("https://demoqa.com/automation-practice-form", timeout=20000)
        page.locator("#firstName").first.fill(first_name, timeout=10000)
        page.locator("#lastName").first.fill(last_name, timeout=10000)
        page.locator("#userEmail").first.fill(email, timeout=10000)

        if gender.lower() == "male":
            page.locator("label[for='gender-radio-1']").first.click(timeout=5000, force=True)
        elif gender.lower() == "female":
            page.locator("label[for='gender-radio-2']").first.click(timeout=5000, force=True)
        elif gender.lower() == "other":
            page.locator("label[for='gender-radio-3']").first.click(timeout=5000, force=True)

        page.locator("#userNumber").first.fill(mobile, timeout=10000)

        return (
            "Filled DemoQA form with profile data: "
            f"{first_name} {last_name}, {email}, {gender}, {mobile}."
        )
    except Exception as e:
        return f"Error filling DemoQA form: {e}"

@tool
def schedule_meeting(title: str, time: str) -> str:
    """Schedule a meeting in Google Calendar. Provide a title and a time (e.g. 'tomorrow at 3pm')."""
    if _send_update:
        _send_update(f"Mocking Google Calendar API: Scheduling '{title}' for {time}...")
    # Mocking actual Calendar API call
    return f"Success! '{title}' has been scheduled for {time} in Google Calendar."

@tool
def send_email(to_email: str, subject: str, body: str) -> str:
    """Send an email from the profile email address to the specified recipient using Gmail API."""
    try:
        send_gmail_message(to_email, subject, body)
        return f"Email sent to {to_email}"
    except Exception as e:
        return f"Error sending email: {e}"


@tool
def send_targeted_emails(
    user_id: int | None = None,
    subscription_active: bool | None = None,
    email_not_null: bool = True,
    delivery_zone: str | None = None,
    subject: str = "",
    body: str = "",
) -> str:
    """Find customers by filters and send the same email to each matching customer email."""
    try:
        rows = fetch_customers(
            user_id=user_id,
            subscription_active=subscription_active,
            email_not_null=email_not_null,
            delivery_zone=delivery_zone,
        )

        if not rows:
            return "No matching customers found."

        sent_emails = []
        skipped_users = []

        for row in rows:
            recipient_email = row.get("email")
            if not recipient_email:
                skipped_users.append(str(row.get("user_id")))
                continue

            send_gmail_message(recipient_email, subject, body)
            sent_emails.append(recipient_email)

        return json.dumps(
            {
                "matched_rows": len(rows),
                "sent_count": len(sent_emails),
                "sent_emails": sent_emails,
                "skipped_users_without_email": skipped_users,
            },
            default=str,
        )
    except Exception as e:
        return f"Error sending targeted emails: {e}"

async def run_agent(user_instruction: str, send_update_callback) -> str:
    global _send_update, p, browser, page
    _send_update = send_update_callback
    
    send_update_callback("Initializing LangChain Agent...")
    
    # Initialize the LLM using Groq
    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
    
    # Define our list of tools
    tools = [
        get_my_profile,
        find_customers,
        send_targeted_emails,
        navigate_to,
        click_element,
        type_text,
        fill_demoqa_form,
        schedule_meeting,
        send_email,
    ]
    llm_with_tools = llm.bind_tools(tools)
    
    messages = [
        ("system", "You are a helpful intelligent assistant. You can read the user's profile data from profile.json, query the customers table in PostgreSQL, automate their browser to fill out forms, and schedule calendar events. When the user asks to send email to a user_id or to customers filtered by columns such as subscription_active, delivery_zone, or email_not_null, first use find_customers or send_targeted_emails to resolve the recipient email addresses from the database, then send the emails. For DemoQA practice form requests, use fill_demoqa_form instead of guessing individual fields. Always use your tools. When a task is complete, summarize what you did.")
    ]
    messages.append(("user", user_instruction))
    
    send_update_callback("Agent is thinking...")
    
    try:
        # Agent loop (running in an async wrapper to not block entirely, though LLM call is sync)
        # For production, we'd use ainvoke or run in executor
        while True:
            # We use an executor to prevent blocking the async loop during the LLM call
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, llm_with_tools.invoke, messages)
            
            messages.append(response)
            
            if not response.tool_calls:
                send_update_callback("Task complete!")
                return response.content
            
            for tool_call in response.tool_calls:
                tool_func = next((t for t in tools if t.name == tool_call['name']), None)
                
                if tool_func:
                    # Run the tool in executor so playwright/file IO doesn't block FastAPI loop
                    tool_result = await loop.run_in_executor(None, tool_func.invoke, tool_call['args'])
                else:
                    tool_result = f"Error: Tool {tool_call['name']} not found."
                
                messages.append(ToolMessage(
                    tool_call_id=tool_call['id'], 
                    name=tool_call['name'], 
                    content=str(tool_result)
                ))
                
                send_update_callback("Thinking about next steps...")

    finally:
        # In a real app we might leave the browser open or close it. We'll close it here.
        if p:
            send_update_callback("Cleaning up browser...")
            p.stop()
            p = None
            browser = None
            page = None
