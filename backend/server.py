
import os
import sys
import json
import sqlite3
import bcrypt
import smtplib
import time
import uuid
import random
import requests
from datetime import datetime
from email.message import EmailMessage
from flask import Flask, request, jsonify
from openai import OpenAI

# =========================
# CONFIGURATION
# =========================

APP_TITLE = "HELIX"
DB_FILE = "helix_v2.db"
SESSION_FILE = "helix_session.json"

# --- ⚠️ EMAIL SETTINGS ⚠️ ---
SMTP_EMAIL = "your_real_email@gmail.com"
SMTP_PASSWORD = "paste_your_16_digit_app_password_here"

# --- MODEL CONFIGURATION ---
MODEL_CONFIG = {
    "Standard": {"id": "hermes-3-llama-3.1-8b", "cost_multiplier": 1, "desc": "⚡"},
    "Thinking": {"id": "glm-4.1v-9b-thinking", "cost_multiplier": 3, "desc": "🧠"},
}
INITIAL_TOKENS = 5000
MAX_MEMORIES = 65
LOCAL_URL = "http://localhost:1234/v1"
PUBLIC_URL = "https://balanced-normally-mink.ngrok-free.app/v1"
API_KEY = "lm-studio"

def data_path(rel_path: str) -> str:
    """Path for runtime data (db, session)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        # Assuming server.py is in /backend, db is in root
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, rel_path)

# =========================
# DATABASE
# =========================

class DatabaseManager:
    def __init__(self) -> None:
        self.path = data_path(DB_FILE)
        self.init_db()

    def init_db(self) -> None:
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password_hash BLOB,
                tokens INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS history (
                email TEXT PRIMARY KEY,
                chat_data TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS notebooks (
                id TEXT PRIMARY KEY,
                email TEXT,
                title TEXT,
                content TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                content TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                email TEXT PRIMARY KEY,
                display_name TEXT,
                bio TEXT,
                avatar_color TEXT,
                avatar_path TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                user_email TEXT,
                name TEXT,
                avatar_color TEXT,
                last_msg TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS dm_messages (
                id TEXT PRIMARY KEY,
                contact_id TEXT,
                role TEXT,
                content TEXT,
                timestamp TEXT,
                is_draft INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS friendships (
                id TEXT PRIMARY KEY,
                user_email TEXT,
                friend_email TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

    def check_exists(self, email: str) -> bool:
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        return res is not None

    def register_final(self, email: str, password: str) -> tuple[bool, str]:
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        try:
            pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
            c.execute("INSERT INTO users VALUES (?, ?, ?)", (email, pw_hash, INITIAL_TOKENS))
            c.execute("INSERT INTO history VALUES (?, ?)", (email, "{}"))
            c.execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?)", (email, email.split("@")[0], "New Helix User", "#8AB4F8", None))
            conn.commit()
            return True, "OK"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def login(self, email: str, password: str) -> tuple[bool, int]:
        conn = sqlite3.connect(self.path)
        data = conn.cursor().execute("SELECT password_hash, tokens FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if data and bcrypt.checkpw(password.encode("utf-8"), data[0]):
            return True, int(data[1])
        return False, 0

    def deduct_tokens(self, email: str, amount: int) -> int:
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        c.execute("UPDATE users SET tokens = MAX(0, tokens - ?) WHERE email=?", (amount, email))
        conn.commit()
        bal = c.execute("SELECT tokens FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        return int(bal[0]) if bal else 0

    def save_chats(self, email: str, chat_dict: dict) -> None:
        conn = sqlite3.connect(self.path)
        conn.cursor().execute("UPDATE history SET chat_data=? WHERE email=?", (json.dumps(chat_dict), email))
        conn.commit()
        conn.close()

    def load_chats(self, email: str) -> dict:
        conn = sqlite3.connect(self.path)
        row = conn.cursor().execute("SELECT chat_data FROM history WHERE email=?", (email,)).fetchone()
        conn.close()
        if not row or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_notebook(self, nid: str, email: str, title: str, content: str) -> None:
        conn = sqlite3.connect(self.path)
        conn.cursor().execute(
            "INSERT OR REPLACE INTO notebooks (id, email, title, content, updated_at) VALUES (?, ?, ?, ?, ?)",
            (nid, email, title, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()

    def load_notebooks_list(self, email: str):
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute(
            "SELECT id, title FROM notebooks WHERE email=? ORDER BY updated_at DESC",
            (email,),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "title": r[1]} for r in res]

    def load_notebook_content(self, nid: str) -> dict:
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT title, content FROM notebooks WHERE id=?", (nid,)).fetchone()
        conn.close()
        return {"title": res[0], "content": res[1]} if res else {"title": "Untitled", "content": ""}

    def add_memory(self, email: str, content: str) -> None:
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        count = c.execute("SELECT COUNT(*) FROM memories WHERE email=?", (email,)).fetchone()[0]
        if count >= MAX_MEMORIES:
            oldest = c.execute("SELECT id FROM memories WHERE email=? ORDER BY id ASC LIMIT 1", (email,)).fetchone()
            if oldest:
                c.execute("DELETE FROM memories WHERE id=?", (oldest[0],))
        c.execute(
            "INSERT INTO memories (email, content, created_at) VALUES (?, ?, ?)",
            (email, content, datetime.now().strftime("%Y-%m-%d")),
        )
        conn.commit()
        conn.close()

    def get_memories(self, email: str):
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute(
            "SELECT id, content FROM memories WHERE email=? ORDER BY id DESC",
            (email,),
        ).fetchall()
        conn.close()
        return [{"id": r[0], "content": r[1]} for r in res]

    def delete_memory(self, mid: int) -> None:
        conn = sqlite3.connect(self.path)
        conn.cursor().execute("DELETE FROM memories WHERE id=?", (mid,))
        conn.commit()
        conn.close()

    def get_profile(self, email: str):
        conn = sqlite3.connect(self.path)
        try:
             res = conn.cursor().execute("SELECT display_name, bio, avatar_color, avatar_path FROM profiles WHERE email=?", (email,)).fetchone()
        except:
             res = conn.cursor().execute("SELECT display_name, bio, avatar_color FROM profiles WHERE email=?", (email,)).fetchone()
             if res: res = res + (None,)
        conn.close()
        if not res:
            return {"display_name": email.split("@")[0], "bio": "New Helix User", "avatar_color": "#8AB4F8", "avatar_path": None}
        return {"display_name": res[0], "bio": res[1], "avatar_color": res[2], "avatar_path": res[3]}

    def save_profile(self, email: str, display_name: str, bio: str, avatar_path: str = None):
        conn = sqlite3.connect(self.path)
        exists = conn.cursor().execute("SELECT 1 FROM profiles WHERE email=?", (email,)).fetchone()
        if exists:
            conn.cursor().execute("UPDATE profiles SET display_name=?, bio=?, avatar_path=? WHERE email=?", (display_name, bio, avatar_path, email))
        else:
            conn.cursor().execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?)", (email, display_name, bio, "#8AB4F8", avatar_path))
        conn.commit()
        conn.close()

    def get_contacts(self, email):
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT id, name, last_msg FROM contacts WHERE user_email=? ORDER BY updated_at DESC", (email,)).fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "last_msg": r[2]} for r in res]

    def add_contact(self, email, name):
        conn = sqlite3.connect(self.path)
        cid = str(uuid.uuid4())
        conn.cursor().execute("INSERT INTO contacts VALUES (?, ?, ?, ?, ?, ?)", (cid, email, name, "#555", "New Chat", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        return cid

    def get_dm_messages(self, contact_id):
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT role, content, is_draft FROM dm_messages WHERE contact_id=? ORDER BY timestamp ASC", (contact_id,)).fetchall()
        conn.close()
        return [{"role": r[0], "content": r[1], "is_draft": r[2]} for r in res]

    def save_dm_message(self, contact_id, role, content, is_draft=0):
        conn = sqlite3.connect(self.path)
        mid = str(uuid.uuid4())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute("INSERT INTO dm_messages VALUES (?, ?, ?, ?, ?, ?)", (mid, contact_id, role, content, ts, is_draft))
        if not is_draft:
            conn.cursor().execute("UPDATE contacts SET last_msg=?, updated_at=? WHERE id=?", (content[:30], ts, contact_id))
        conn.commit()
        conn.close()

    def send_friend_request(self, user_email, target_email):
        if not self.check_exists(target_email):
            return False, "User not found."
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        existing = c.execute("SELECT status FROM friendships WHERE (user_email=? AND friend_email=?) OR (user_email=? AND friend_email=?)",
                             (user_email, target_email, target_email, user_email)).fetchone()
        if existing:
            return False, f"Request already {existing[0]}."
        fid = str(uuid.uuid4())
        c.execute("INSERT INTO friendships VALUES (?, ?, ?, ?, ?)", (fid, user_email, target_email, "pending", datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        conn.close()
        return True, "Request sent!"

    def get_friendships(self, email):
        conn = sqlite3.connect(self.path)
        friends = []
        rows = conn.cursor().execute("SELECT user_email, friend_email, status FROM friendships WHERE (user_email=? OR friend_email=?) AND status='accepted'", (email, email)).fetchall()
        for u, f, s in rows:
            other = f if u == email else u
            p = self.get_profile(other)
            friends.append({"email": other, "name": p["display_name"], "avatar": p["avatar_color"], "status": "accepted"})
        conn.close()
        return friends

    def get_pending_requests(self, email):
        conn = sqlite3.connect(self.path)
        rows = conn.cursor().execute("SELECT id, user_email FROM friendships WHERE friend_email=? AND status='pending'", (email,)).fetchall()
        pending = []
        for rid, requester_email in rows:
             p = self.get_profile(requester_email)
             pending.append({"id": rid, "email": requester_email, "name": p["display_name"]})
        conn.close()
        return pending

    def accept_friend_request(self, request_id):
        conn = sqlite3.connect(self.path)
        conn.cursor().execute("UPDATE friendships SET status='accepted' WHERE id=?", (request_id,))
        conn.commit()
        conn.close()

# =========================
# AI & EMAIL UTILS
# =========================

def get_working_client() -> OpenAI:
    try:
        if requests.get(f"{LOCAL_URL}/models", timeout=1).status_code == 200:
            return OpenAI(base_url=LOCAL_URL, api_key=API_KEY)
    except Exception:
        pass
    return OpenAI(base_url=PUBLIC_URL, api_key=API_KEY)

client = get_working_client()
db = DatabaseManager()

def send_otp_email(to_email: str, otp_code: str) -> tuple[bool, str]:
    try:
        msg = EmailMessage()
        msg.set_content(f"Verification code: {otp_code}")
        msg["Subject"] = "Helix Code"
        msg["From"] = SMTP_EMAIL
        msg["To"] = to_email

        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True, "Code sent!"
    except Exception:
        return False, "Email failed."

# =========================
# FLASK SERVER
# =========================

app = Flask(__name__)

# --- AUTH ---

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    success, tokens = db.login(data['email'], data['password'])
    if success:
        return jsonify({"status": "ok", "tokens": tokens})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/send-otp', methods=['POST'])
def send_otp():
    data = request.json
    email = data['email']
    if db.check_exists(email):
        return jsonify({"status": "error", "message": "Account exists"}), 409
    otp = str(random.randint(100000, 999999))
    # In production, actually send email. Here we return it for testing if email fails
    # success, msg = send_otp_email(email, otp)
    # We will assume success for dev/testing locally without secrets
    # But let's try calling it if credentials were real
    # For now, just return it so frontend can use it
    return jsonify({"status": "ok", "otp": otp})

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    ok, msg = db.register_final(data['email'], data['password'])
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": msg}), 400

# --- CHAT ---

@app.route('/chat/load', methods=['POST'])
def load_chats():
    data = request.json
    chats = db.load_chats(data['email'])
    return jsonify(chats)

@app.route('/chat/save', methods=['POST'])
def save_chats():
    data = request.json
    db.save_chats(data['email'], data['chats'])
    return jsonify({"status": "ok"})

@app.route('/chat/stream', methods=['POST'])
def chat_stream():
    # This endpoint will be a generator for Server-Sent Events (SSE)
    # Payload: { messages: [], model: "Standard" }
    from flask import Response, stream_with_context
    req_data = request.json
    messages = req_data.get('messages', [])
    model_key = req_data.get('model', 'Standard')

    def generate():
        try:
            stream = client.chat.completions.create(
                model=MODEL_CONFIG[model_key]["id"],
                messages=messages,
                temperature=0.7,
                stream=True,
            )
            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    c = delta.content
                    full_response += c
                    yield f"data: {json.dumps({'content': c})}\n\n"

            # Deduct tokens (Optional logic here or client side triggers it)
            # yield f"data: {json.dumps({'done': True, 'full': full_response})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/tokens/deduct', methods=['POST'])
def deduct_tokens():
    data = request.json
    # calc cost
    text = data.get('text', '')
    model = data.get('model', 'Standard')
    cost = len(text.split()) * int(MODEL_CONFIG[model]["cost_multiplier"])
    new_bal = db.deduct_tokens(data['email'], cost)
    return jsonify({"balance": new_bal})

# --- NOTEBOOKS ---

@app.route('/notebooks/list', methods=['POST'])
def list_notebooks():
    data = request.json
    return jsonify(db.load_notebooks_list(data['email']))

@app.route('/notebooks/get', methods=['POST'])
def get_notebook():
    data = request.json
    return jsonify(db.load_notebook_content(data['id']))

@app.route('/notebooks/save', methods=['POST'])
def save_notebook():
    data = request.json
    db.save_notebook(data['id'], data['email'], data['title'], data['content'])
    return jsonify({"status": "ok"})

# --- DMS / PROFILE ---

@app.route('/profile', methods=['POST'])
def get_profile():
    data = request.json
    return jsonify(db.get_profile(data['email']))

@app.route('/profile/save', methods=['POST'])
def update_profile():
    data = request.json
    db.save_profile(data['email'], data['display_name'], data['bio'], data['avatar_path'])
    return jsonify({"status": "ok"})

@app.route('/dms/friends', methods=['POST'])
def get_friends():
    data = request.json
    return jsonify({
        "friends": db.get_friendships(data['email']),
        "pending": db.get_pending_requests(data['email']),
        "contacts": db.get_contacts(data['email'])
    })

@app.route('/dms/load', methods=['POST'])
def load_dm_thread():
    data = request.json
    return jsonify(db.get_dm_messages(data['contact_id']))

@app.route('/dms/send', methods=['POST'])
def send_dm():
    data = request.json
    db.save_dm_message(data['contact_id'], data['role'], data['content'])
    return jsonify({"status": "ok"})

@app.route('/dms/add_friend', methods=['POST'])
def add_friend():
    data = request.json
    ok, msg = db.send_friend_request(data['user_email'], data['target_email'])
    return jsonify({"status": "ok" if ok else "error", "message": msg})

@app.route('/dms/accept_friend', methods=['POST'])
def accept_friend():
    data = request.json
    db.accept_friend_request(data['request_id'])
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
