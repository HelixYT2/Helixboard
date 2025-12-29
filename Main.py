
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

import pyperclip
import time
import threading
import sys
import os
import json
import uuid
import requests
import sqlite3
import bcrypt
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime

from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps

# =========================
# CONFIGURATION
# =========================

APP_TITLE = "HELIX"

LOGO_FILENAME = "helix_logo.png"   # packaged asset
DB_FILE = "helix_v2.db"            # runtime data
SESSION_FILE = "helix_session.json"  # runtime data

# --- ⚠️ EMAIL SETTINGS ⚠️ ---
# Use environment variables in real deployments.
SMTP_EMAIL = "your_real_email@gmail.com"
SMTP_PASSWORD = "paste_your_16_digit_app_password_here"

# --- ADMIN SECRETS ---
ADMIN_EMAIL = "admin@helix.com"

# --- MODEL CONFIGURATION ---
MODEL_CONFIG = {
    "Standard": {"id": "hermes-3-llama-3.1-8b", "cost_multiplier": 1, "desc": "⚡"},
    "Thinking": {"id": "glm-4.1v-9b-thinking", "cost_multiplier": 3, "desc": "🧠"},
}

# --- TOKEN ECONOMY ---
INITIAL_TOKENS = 5000
MAX_MEMORIES = 65

# --- NETWORK SETTINGS ---
LOCAL_URL = "http://localhost:1234/v1"
PUBLIC_URL = "https://balanced-normally-mink.ngrok-free.app/v1"
API_KEY = "lm-studio"

# --- THEME (Gemini-inspired) ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

BG_DARK = "#131314"
BG_SIDEBAR = "#1E1F20"
BG_CARD = "#28292A"
BG_INPUT = "#1E1F20"
HELIX_PURPLE = "#8AB4F8"
HELIX_HOVER = "#669DF6"
TEXT_WHITE = "#E3E3E3"
TEXT_GRAY = "#A8A8A8"
PLACEHOLDER_GRAY = "#5F6368"

FONT_HEADER = ("Google Sans", 26, "bold")
FONT_SUBHEADER = ("Google Sans", 18, "bold")
FONT_NORMAL = ("Google Sans", 14)
FONT_BOLD = ("Google Sans", 14, "bold")
FONT_INPUT = ("Google Sans", 15)
FONT_SMALL = ("Google Sans", 12)

PROMPTS = {
    "Fix": "Output ONLY the corrected version. Do NOT explain.",
    "Chat": "You are Helix, an intelligent AI assistant. Answer clearly."
}

# =========================
# PATHS (assets vs runtime data)
# =========================

def asset_path(rel_path: str) -> str:
    """Path for packaged assets (logo, icons, etc)."""
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)

def data_path(rel_path: str) -> str:
    """Path for runtime data (db, session)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(".")
    return os.path.join(base, rel_path)

# =========================
# IMAGE UTILS
# =========================

def make_circle(pil_img: Image.Image) -> Image.Image:
    pil_img = pil_img.convert("RGBA")
    size = pil_img.size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    output = ImageOps.fit(pil_img, mask.size, centering=(0.5, 0.5))
    output.putalpha(mask)
    return output

# =========================
# SESSION & EMAIL
# =========================

def save_session(email: str) -> None:
    try:
        with open(data_path(SESSION_FILE), "w", encoding="utf-8") as f:
            json.dump({"email": email, "expiry": time.time() + 604800}, f)
    except Exception:
        pass

def load_session() -> str | None:
    try:
        path = data_path(SESSION_FILE)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("expiry", 0) > time.time():
                return data.get("email")
    except Exception:
        pass
    return None

def clear_session() -> None:
    try:
        path = data_path(SESSION_FILE)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass

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
        # DM Tables
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
            # Init profile
            c.execute("INSERT INTO profiles VALUES (?, ?, ?, ?)", (email, email.split("@")[0], "New Helix User", "#8AB4F8"))
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

    def get_token_balance(self, email: str) -> int:
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT tokens FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        return int(res[0]) if res else 0

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
        return res

    def load_notebook_content(self, nid: str) -> tuple[str, str]:
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT title, content FROM notebooks WHERE id=?", (nid,)).fetchone()
        conn.close()
        return (res[0], res[1]) if res else ("Untitled", "")

    def add_memory(self, email: str, content: str) -> None:
        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        # Enforce limit by deleting oldest if count >= MAX_MEMORIES
        count = c.execute("SELECT COUNT(*) FROM memories WHERE email=?", (email,)).fetchone()[0]
        if count >= MAX_MEMORIES:
            # Delete oldest
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
        return res

    def delete_memory(self, mid: int) -> None:
        conn = sqlite3.connect(self.path)
        conn.cursor().execute("DELETE FROM memories WHERE id=?", (mid,))
        conn.commit()
        conn.close()

    def get_profile(self, email: str):
        conn = sqlite3.connect(self.path)
        # Try to get avatar_path (might not exist in old rows, so handle gracefully)
        try:
             res = conn.cursor().execute("SELECT display_name, bio, avatar_color, avatar_path FROM profiles WHERE email=?", (email,)).fetchone()
        except:
             res = conn.cursor().execute("SELECT display_name, bio, avatar_color FROM profiles WHERE email=?", (email,)).fetchone()
             if res: res = res + (None,)

        conn.close()
        if not res:
            return (email.split("@")[0], "New Helix User", "#8AB4F8", None)
        return res

    def save_profile(self, email: str, display_name: str, bio: str, avatar_path: str = None):
        conn = sqlite3.connect(self.path)
        # Check if exists
        exists = conn.cursor().execute("SELECT 1 FROM profiles WHERE email=?", (email,)).fetchone()
        if exists:
            conn.cursor().execute("UPDATE profiles SET display_name=?, bio=?, avatar_path=? WHERE email=?", (display_name, bio, avatar_path, email))
        else:
            conn.cursor().execute("INSERT INTO profiles VALUES (?, ?, ?, ?, ?)", (email, display_name, bio, "#8AB4F8", avatar_path))
        conn.commit()
        conn.close()

    # --- DM METHODS ---
    def get_contacts(self, email):
        conn = sqlite3.connect(self.path)
        res = conn.cursor().execute("SELECT id, name, last_msg FROM contacts WHERE user_email=? ORDER BY updated_at DESC", (email,)).fetchall()
        conn.close()
        return res

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
        return res

    def save_dm_message(self, contact_id, role, content, is_draft=0):
        conn = sqlite3.connect(self.path)
        mid = str(uuid.uuid4())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute("INSERT INTO dm_messages VALUES (?, ?, ?, ?, ?, ?)", (mid, contact_id, role, content, ts, is_draft))
        if not is_draft:
            conn.cursor().execute("UPDATE contacts SET last_msg=?, updated_at=? WHERE id=?", (content[:30], ts, contact_id))
        conn.commit()
        conn.close()

    # --- FRIENDSHIP METHODS ---
    def send_friend_request(self, user_email, target_email):
        # Check if user exists
        if not self.check_exists(target_email):
            return False, "User not found."

        conn = sqlite3.connect(self.path)
        c = conn.cursor()
        # Check if already friends or pending
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
        """Returns list of friends (accepted) and pending requests."""
        conn = sqlite3.connect(self.path)
        # We want to find anyone where status='accepted' AND email is involved

        # Get accepted friends
        friends = []
        rows = conn.cursor().execute("SELECT user_email, friend_email, status FROM friendships WHERE (user_email=? OR friend_email=?) AND status='accepted'", (email, email)).fetchall()
        for u, f, s in rows:
            other = f if u == email else u
            # Get profile info
            p = self.get_profile(other)
            friends.append({"email": other, "name": p[0], "avatar": p[2], "status": "accepted"})

        conn.close()
        return friends

    def get_pending_requests(self, email):
        conn = sqlite3.connect(self.path)
        # Find requests where friend_email == email AND status == 'pending'
        rows = conn.cursor().execute("SELECT id, user_email FROM friendships WHERE friend_email=? AND status='pending'", (email,)).fetchall()
        pending = []
        for rid, requester_email in rows:
             p = self.get_profile(requester_email)
             pending.append({"id": rid, "email": requester_email, "name": p[0]})
        conn.close()
        return pending

    def accept_friend_request(self, request_id):
        conn = sqlite3.connect(self.path)
        conn.cursor().execute("UPDATE friendships SET status='accepted' WHERE id=?", (request_id,))
        conn.commit()
        conn.close()


# =========================
# AI CLIENT
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

# =========================
# FLOATING WIDGET
# =========================

class FloatingWidget(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.geometry("80x80+100+100")
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color="#000001")
        self.attributes("-transparentcolor", "#000001")

        try:
            logo = Image.open(asset_path(LOGO_FILENAME))
            self.logo_image = ctk.CTkImage(light_image=make_circle(logo), size=(60, 60))
            self.btn = ctk.CTkButton(
                self,
                text="",
                image=self.logo_image,
                width=60,
                height=60,
                corner_radius=30,
                fg_color="#000001",
                hover_color="#000001",
                command=self.on_click,
            )
        except Exception:
            self.btn = ctk.CTkButton(
                self,
                text="H",
                font=FONT_HEADER,
                width=60,
                height=60,
                corner_radius=30,
                fg_color=HELIX_PURPLE,
                command=self.on_click,
                text_color="black",
            )

        self.btn.place(relx=0.5, rely=0.5, anchor="center")

        self.bind("<ButtonPress-1>", self.start_move)
        self.bind("<B1-Motion>", self.do_move)

        self.hide_timer = None
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.start_hide_timer()

    def start_move(self, e):
        self.x = e.x
        self.y = e.y

    def do_move(self, e):
        self.geometry(f"+{self.winfo_x() + (e.x - self.x)}+{self.winfo_y() + (e.y - self.y)}")

    def on_click(self):
        self.parent.show_window("clipboard")

    def on_enter(self, _):
        self.attributes("-alpha", 1.0)
        if self.hide_timer:
            try:
                self.after_cancel(self.hide_timer)
            except Exception:
                pass

    def on_leave(self, _):
        self.start_hide_timer()

    def start_hide_timer(self):
        self.hide_timer = self.after(10000, lambda: self.attributes("-alpha", 0.05))

# =========================
# CANVAS DRAFTING OVERLAY
# =========================

class CanvasDraftingOverlay(ctk.CTkFrame):
    def __init__(self, parent_widget, controller, initial_text):
        super().__init__(parent_widget, fg_color=BG_DARK, corner_radius=0)
        self.app = controller
        self.initial_text = initial_text

        self.grid_columnconfigure(0, weight=1) # Left: Instructions
        self.grid_columnconfigure(1, weight=2) # Right: Final Output
        self.grid_rowconfigure(0, weight=1)

        # LEFT PANE: Instructions
        left_pane = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, corner_radius=0)
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 2))

        ctk.CTkLabel(left_pane, text="INSTRUCTIONS", font=FONT_BOLD, text_color="#AAA").pack(anchor="w", padx=20, pady=20)

        self.chat_scroll = ctk.CTkScrollableFrame(left_pane, fg_color="transparent")
        self.chat_scroll.pack(fill="both", expand=True, padx=10)

        # Instruction Input (Message Box Style)
        inp_container = ctk.CTkFrame(left_pane, fg_color="transparent")
        inp_container.pack(fill="x", side="bottom", padx=15, pady=20)

        self.inp_pill = ctk.CTkFrame(inp_container, fg_color=BG_INPUT, height=60, corner_radius=30)
        self.inp_pill.pack(fill="x")

        self.inp_box = ctk.CTkTextbox(self.inp_pill, height=40, fg_color="transparent", font=FONT_INPUT, wrap="word")
        self.inp_box.pack(side="left", fill="x", expand=True, padx=15, pady=10)
        self.app.setup_textbox_placeholder(self.inp_box, "Describe what to write...", self.run_draft)

        ctk.CTkButton(self.inp_pill, text="➤", width=40, height=40, corner_radius=20, fg_color=HELIX_PURPLE, text_color="black", font=("Arial", 16), command=self.run_draft).pack(side="right", padx=10)

        # RIGHT PANE: Final Output
        right_pane = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        right_pane.grid(row=0, column=1, sticky="nsew")

        header = ctk.CTkFrame(right_pane, fg_color="transparent", height=50)
        header.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(header, text="DRAFT PREVIEW", font=FONT_BOLD, text_color="#AAA").pack(side="left")

        ctk.CTkButton(header, text="Insert into Notebook", width=140, fg_color=HELIX_PURPLE, text_color="black", command=self.insert_and_close).pack(side="right")
        ctk.CTkButton(header, text="Cancel", width=80, fg_color="transparent", border_width=1, border_color="#555", command=self.close).pack(side="right", padx=10)

        self.preview_box = ctk.CTkTextbox(right_pane, font=FONT_NORMAL, fg_color=BG_INPUT)
        self.preview_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.preview_box.insert("0.0", initial_text)

    def run_draft(self):
        inst = self.inp_box.get("0.0", "end").strip()
        if not inst or getattr(self.inp_box, "has_placeholder", False):
            return

        current = self.preview_box.get("0.0", "end").strip()

        # Clear Input
        self.inp_box.delete("0.0", "end")
        self.app.setup_textbox_placeholder(self.inp_box, "Describe what to write...", self.run_draft)

        # Add user msg to left (History)
        lbl = ctk.CTkLabel(self.chat_scroll, text=inst, fg_color=BG_CARD, corner_radius=10, padx=10, pady=5, anchor="w", justify="left", wraplength=200)
        lbl.pack(fill="x", pady=5, padx=5)

        # Run AI Stream
        msgs = [
            {"role": "system", "content": "You are an AI writing assistant. Output ONLY the updated text based on the user's instruction. Do not converse. Do not add introductions."},
            {"role": "user", "content": f"Current Text:\n{current}\n\nInstruction: {inst}"}
        ]

        # Hide input while generating
        self.inp_pill.pack_forget()

        def on_complete():
            self.inp_pill.pack(fill="x")

        def run_wrapper():
            self.app.run_ai_stream(msgs, self.preview_box, False)
            self.after(0, on_complete)

        threading.Thread(
            target=run_wrapper,
            daemon=True
        ).start()

    def insert_and_close(self):
        final_text = self.preview_box.get("0.0", "end").strip()
        self.app.notebook.delete("0.0", "end")
        self.app.notebook.insert("0.0", final_text)
        self.close()

    def close(self):
        self.app.animate_overlay_close(self)
        self.app.canvas_overlay = None

# =========================
# SETTINGS OVERLAY (ANIMATED)
# =========================

class SettingsOverlay(ctk.CTkFrame):
    def __init__(self, parent_widget, controller, dbm: DatabaseManager, current_user: str, on_logout):
        super().__init__(parent_widget, fg_color=BG_DARK, corner_radius=0)
        self.app = controller
        self.db = dbm
        self.current_user = current_user
        self.on_logout = on_logout

        # Grid layout
        self.grid_columnconfigure(0, weight=0) # sidebar
        self.grid_columnconfigure(1, weight=1) # content
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=250, fg_color=BG_SIDEBAR, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Header in sidebar
        ctk.CTkLabel(self.sidebar, text="SETTINGS", font=FONT_HEADER, text_color="white").pack(
            anchor="w", padx=30, pady=(40, 20)
        )

        self.nav_btns = {}

        # Tabs
        self.create_nav_btn("Profile", "Profile")
        self.create_nav_btn("Context", "Context")
        self.create_nav_btn("Personalization", "Personalization")
        self.create_nav_btn("General", "General")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=BG_CARD).pack(fill="x", pady=20, padx=30)

        ctk.CTkButton(
            self.sidebar,
            text="Close",
            fg_color=BG_CARD,
            hover_color=BG_INPUT,
            anchor="w",
            text_color=TEXT_WHITE,
            font=FONT_NORMAL,
            height=45,
            corner_radius=22,
            command=self.close
        ).pack(fill="x", padx=20, pady=5)

        ctk.CTkButton(
            self.sidebar,
            text="Log out",
            fg_color="transparent",
            hover_color=BG_CARD,
            anchor="w",
            text_color="#ff5555",
            font=FONT_NORMAL,
            height=45,
            corner_radius=22,
            command=self.do_logout_click
        ).pack(fill="x", padx=20, pady=5)

        # Content Area
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=50, pady=50)

        # Initial Page
        self.switch_page("Profile")

    def create_nav_btn(self, text, page):
        btn = ctk.CTkButton(
            self.sidebar,
            text=text,
            fg_color="transparent",
            hover_color=BG_CARD,
            anchor="w",
            font=FONT_NORMAL,
            height=45,
            corner_radius=22,
            command=lambda: self.switch_page(page)
        )
        btn.pack(fill="x", padx=20, pady=5)
        self.nav_btns[page] = btn

    def do_logout_click(self):
        self.close()
        self.on_logout()

    def close(self):
        # Slide down animation
        self.app.animate_overlay_close(self)

    def switch_page(self, page):
        # Update styling
        for p, b in self.nav_btns.items():
            b.configure(fg_color=BG_CARD if p == page else "transparent")

        # Clear content
        for w in self.content.winfo_children():
            w.destroy()

        # Title
        ctk.CTkLabel(self.content, text=page, font=FONT_HEADER, text_color="white").pack(anchor="w", pady=(0, 20))

        if page == "Profile":
            self.build_profile_page()
        elif page == "Context":
            self.build_context_page()
        elif page == "Personalization":
            self.build_personalization_page()
        elif page == "General":
            self.build_general_page()

    def build_profile_page(self):
        # Fetch data
        dname, bio, color, av_path = self.db.get_profile(self.current_user)
        self.new_avatar_path = av_path # store for saving

        ctk.CTkLabel(self.content, text="Public Profile (Saved Locally)", font=FONT_NORMAL, text_color=TEXT_GRAY).pack(anchor="w", pady=(0, 20))

        # Avatar
        av_row = ctk.CTkFrame(self.content, fg_color="transparent")
        av_row.pack(anchor="w", pady=10)

        self.lbl_avatar_status = ctk.CTkLabel(av_row, text="Avatar: Default" if not av_path else "Avatar: Custom", font=FONT_SMALL, text_color="gray")
        self.lbl_avatar_status.pack(side="left", padx=(0, 10))

        ctk.CTkButton(av_row, text="Change Avatar", width=120, height=30, fg_color=BG_CARD, command=self.pick_avatar).pack(side="left")

        # Display Name
        ctk.CTkLabel(self.content, text="Display Name", font=FONT_BOLD).pack(anchor="w", pady=(10, 5))
        self.entry_dname = ctk.CTkEntry(self.content, width=300, height=40, font=FONT_NORMAL, fg_color=BG_INPUT, border_width=0, corner_radius=10)
        self.entry_dname.pack(anchor="w")
        self.entry_dname.insert(0, dname)

        # Bio
        ctk.CTkLabel(self.content, text="Bio", font=FONT_BOLD).pack(anchor="w", pady=(20, 5))
        self.entry_bio = ctk.CTkTextbox(self.content, width=400, height=100, font=FONT_NORMAL, fg_color=BG_INPUT, border_width=0, corner_radius=10)
        self.entry_bio.pack(anchor="w")
        self.entry_bio.insert("0.0", bio)

        # Save
        ctk.CTkButton(self.content, text="Save Changes", fg_color=HELIX_PURPLE, text_color="black", width=150, height=40, corner_radius=20, command=self.save_profile).pack(anchor="w", pady=30)

    def pick_avatar(self):
        path = tk.filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if path:
             # Save to user_data/avatars
             # Ensure dir
             base_dir = data_path("user_data/avatars")
             os.makedirs(base_dir, exist_ok=True)

             ext = os.path.splitext(path)[1]
             new_name = f"{uuid.uuid4()}{ext}"
             dest = os.path.join(base_dir, new_name)

             try:
                 import shutil
                 shutil.copy(path, dest)
                 self.new_avatar_path = dest
                 self.lbl_avatar_status.configure(text="Avatar: Selected (Click Save)")
             except Exception as e:
                 messagebox.showerror("Error", f"Failed to load image: {e}")

    def save_profile(self):
        dn = self.entry_dname.get().strip()
        bio = self.entry_bio.get("0.0", "end").strip()
        self.db.save_profile(self.current_user, dn, bio, self.new_avatar_path)
        messagebox.showinfo("Success", "Profile updated! Restart to see changes.")

    def build_context_page(self):
        ctk.CTkLabel(self.content, text="Notebook Context (RAG)", font=FONT_SUBHEADER).pack(anchor="w", pady=(10, 10))
        ctk.CTkLabel(self.content, text="Enable this to let Helix read your notebooks to answer questions.", text_color=TEXT_GRAY).pack(anchor="w", pady=(0, 20))

        self.var_context_active = ctk.BooleanVar(value=self.app.use_notebook_context)

        def toggle_ctx():
            self.app.use_notebook_context = self.var_context_active.get()

        ctk.CTkSwitch(self.content, text="Enable Notebook Context", variable=self.var_context_active, command=toggle_ctx, progress_color=HELIX_PURPLE).pack(anchor="w", pady=10)

        ctk.CTkLabel(self.content, text="Available Notebooks:", font=FONT_BOLD).pack(anchor="w", pady=(20, 10))

        # List of notebooks
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent", height=300)
        scroll.pack(fill="both", expand=True)

        notebooks = self.db.load_notebooks_list(self.current_user)
        if not notebooks:
            ctk.CTkLabel(scroll, text="No notebooks found.", text_color="gray").pack(pady=20)

        for nid, title in notebooks:
            # For now, all are included if enabled. Later: individual selection.
            row = ctk.CTkFrame(scroll, fg_color=BG_CARD)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="📓 " + (title or "Untitled"), anchor="w").pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(row, text="Active", text_color="#555", font=FONT_SMALL).pack(side="right", padx=10)

    def build_personalization_page(self):
        ctk.CTkLabel(self.content, text="Memories (Max 65)", font=FONT_SUBHEADER).pack(anchor="w", pady=(10, 10))

        # Add Input
        add_row = ctk.CTkFrame(self.content, fg_color="transparent")
        add_row.pack(fill="x", pady=10)

        self.mem_entry = ctk.CTkEntry(add_row, placeholder_text="Add a new memory...", height=45, fg_color=BG_INPUT, border_width=0, corner_radius=22, font=FONT_INPUT)
        self.mem_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        ctk.CTkButton(add_row, text="Add", width=80, height=45, fg_color=HELIX_PURPLE, text_color="black", corner_radius=22, command=self.add_mem).pack(side="right")

        # List
        self.mem_scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent", height=400)
        self.mem_scroll.pack(fill="both", expand=True)
        self.refresh_memories()

    def refresh_memories(self):
        for w in self.mem_scroll.winfo_children(): w.destroy()
        mems = self.db.get_memories(self.current_user)

        for m_id, content in mems:
            row = ctk.CTkFrame(self.mem_scroll, fg_color=BG_CARD, corner_radius=15)
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=content, anchor="w", text_color="white", wraplength=500).pack(side="left", padx=15, pady=10)
            ctk.CTkButton(row, text="Delete", width=60, height=30, fg_color="#333", hover_color="#550000", corner_radius=15, command=lambda x=m_id: self.del_mem(x)).pack(side="right", padx=10)

    def add_mem(self):
        txt = self.mem_entry.get().strip()
        if not txt: return
        self.db.add_memory(self.current_user, txt)
        self.mem_entry.delete(0, "end")
        self.refresh_memories()

    def del_mem(self, mid):
        self.db.delete_memory(mid)
        self.refresh_memories()

    def build_general_page(self):
        ctk.CTkLabel(self.content, text="Appearance", font=FONT_SUBHEADER).pack(anchor="w", pady=(10, 20))

        row = ctk.CTkFrame(self.content, fg_color=BG_CARD, corner_radius=15, height=60)
        row.pack(fill="x", pady=5)
        row.pack_propagate(False)

        ctk.CTkLabel(row, text="App Theme", font=FONT_NORMAL, text_color="white").pack(side="left", padx=20)

        self.theme_var = ctk.StringVar(value=ctk.get_appearance_mode())

        def toggle_theme():
            mode = self.theme_var.get()
            ctk.set_appearance_mode(mode)

        seg = ctk.CTkSegmentedButton(row, values=["Dark", "Light"], variable=self.theme_var, command=lambda x: toggle_theme())
        seg.pack(side="right", padx=20)

# =========================
# CHAT UI HELPERS (bubbles)
# =========================

class BubbleMessage:
    """A message row in the chat (user bubble or assistant text block)."""

    def __init__(self, parent, role: str, text: str, max_width_px: int):
        self.role = role
        self.text = text
        self.container = ctk.CTkFrame(parent, fg_color="transparent")
        self.container.grid_columnconfigure(0, weight=1)

        self.max_width_px = max_width_px

        if role == "user":
            # right-aligned bubble
            self.bubble = ctk.CTkFrame(
                self.container,
                fg_color=BG_CARD,
                corner_radius=18,
                border_width=1,
                border_color=HELIX_PURPLE,
            )
            # Use Label for auto-resizing
            self.label = ctk.CTkLabel(
                self.bubble,
                text=text,
                font=FONT_NORMAL,
                text_color=TEXT_WHITE,
                fg_color="transparent",
                wraplength=max_width_px - 40, # Roughly bubble width minus padding
                justify="left",
                anchor="w"
            )
            self.label.pack(padx=15, pady=10)

            self.bubble.grid(row=0, column=0, sticky="e", padx=(80, 0), pady=10)

        else:
            # assistant: text block + actions
            self.bubble = ctk.CTkFrame(self.container, fg_color="transparent")

            self.textbox = ctk.CTkTextbox(
                self.bubble,
                font=FONT_NORMAL,
                text_color=TEXT_WHITE,
                fg_color="transparent",
                wrap="word",
                height=0,
                activate_scrollbars=False
            )
            self.textbox.insert("0.0", text)
            self.textbox.configure(state="disabled")
            self.textbox.pack(anchor="w", fill="x", expand=True)

            # Action Row (Copy / Edit)
            self.actions = ctk.CTkFrame(self.bubble, fg_color="transparent", height=30)
            self.actions.pack(anchor="w", pady=(5, 0))

            ctk.CTkButton(self.actions, text="📄", width=30, height=30, fg_color="transparent", hover_color=BG_INPUT, command=self.copy_text).pack(side="left", padx=(0, 5))

            self.bubble.grid(row=0, column=0, sticky="ew", padx=(0, 40), pady=12)

        # Initial size calc
        self.resize_textbox()

    def resize_textbox(self):
        # Rough calc: lines * line_height
        if not hasattr(self, 'textbox'): return

        # This is a heuristic because CTkTextbox auto-sizing is tricky
        lines = self.text.count('\n') + (len(self.text) / 60) # approx chars per line
        h = max(40, int(lines * 24) + 30) # Increased padding
        self.textbox.configure(height=h)

    def grid(self, row: int):
        self.container.grid(row=row, column=0, sticky="ew")
        return self

    def set_text(self, txt: str):
        self.text = txt
        if self.role == "user":
             self.label.configure(text=txt)
        else:
            self.textbox.configure(state="normal")
            self.textbox.delete("0.0", "end")
            self.textbox.insert("0.0", txt)
            self.textbox.configure(state="disabled")
            self.resize_textbox()

    def append_text(self, more: str):
        self.text += more
        if self.role == "user":
             self.label.configure(text=self.text)
        else:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", more)
            self.textbox.configure(state="disabled")
            self.resize_textbox()

    def set_wraplength(self, px: int):
        if self.role == "user":
             self.label.configure(wraplength=px - 40)
        else:
             pass

    def copy_text(self):
        pyperclip.copy(self.text)

# =========================
# MAIN APP
# =========================

class HelixApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1366x900")
        self.configure(fg_color=BG_DARK)

        # state
        self.current_user = None
        self.token_balance = 0
        self.saved_chats: dict = {}
        self.current_chat_id: str | None = None

        self.current_model_key = "Standard"
        self.current_note_id: str | None = None
        self.attach_notebook_to_chat = False
        self.use_notebook_context = False # Global context toggle

        self.active_tab = "Talk to AI"
        self.is_animating = False

        self.pending_email = ""
        self.pending_pass = ""
        self.pending_otp = ""

        self.settings_overlay = None

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self.setup_login_screen()
        self.setup_otp_screen()
        self.setup_main_app()

        # session restore
        cached = load_session()
        if cached:
            self.current_user = cached
            self.token_balance = db.get_token_balance(self.current_user)
            self.show_app()
        else:
            self.show_login()

    # ---------- UI UTIL ----------
    def setup_textbox_placeholder(self, textbox: ctk.CTkTextbox, placeholder_text: str, submit_func):
        textbox.delete("0.0", "end")
        textbox.insert("0.0", placeholder_text)
        textbox.configure(text_color=PLACEHOLDER_GRAY)
        textbox.has_placeholder = True

        def on_focus_in(_):
            if getattr(textbox, "has_placeholder", False):
                textbox.delete("0.0", "end")
                textbox.configure(text_color=TEXT_WHITE)
                textbox.has_placeholder = False

        def on_focus_out(_):
            if not textbox.get("0.0", "end").strip():
                textbox.delete("0.0", "end")
                textbox.insert("0.0", placeholder_text)
                textbox.configure(text_color=PLACEHOLDER_GRAY)
                textbox.has_placeholder = True

        def on_enter(e):
            # Shift+Enter creates newline
            if e.state & 0x0001:
                return
            if not getattr(textbox, "has_placeholder", False):
                submit_func()
            return "break"

        textbox.bind("<FocusIn>", on_focus_in)
        textbox.bind("<FocusOut>", on_focus_out)
        textbox.bind("<Return>", on_enter)

    def scroll_chat_to_bottom(self):
        canvas = getattr(self.chat_scroll, "_parent_canvas", None)
        if canvas is None:
            canvas = getattr(self.chat_scroll, "_canvas", None)
        if canvas is not None:
            try:
                canvas.yview_moveto(1.0)
            except Exception:
                pass

    # ---------- ANIMATION HELPER ----------
    def animate_slide_page(self, old_frame, new_frame, direction="right"):
        self.is_animating = True
        # We need to use place for sliding
        # Assume both frames are children of self.pages_container

        # Dimensions
        w = self.pages_container.winfo_width()
        h = self.pages_container.winfo_height()

        # Start positions
        # if direction is right (navigating to right tab), new frame comes from right (x=1)
        start_x = 1.0 if direction == "right" else -1.0

        new_frame.place(relx=start_x, rely=0, relwidth=1, relheight=1)
        new_frame.lift()
        old_frame.place(relx=0, rely=0, relwidth=1, relheight=1) # Ensure visible

        steps = 15
        dt = 10 # ms

        def step(i):
            if i > steps:
                new_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
                old_frame.place_forget() # Hide old
                self.is_animating = False
                return

            # Linear interpolation
            progress = i / steps
            # New frame moves from start_x to 0
            curr_new = start_x * (1 - progress)
            # Old frame moves from 0 to -start_x
            curr_old = -start_x * progress

            new_frame.place(relx=curr_new, rely=0, relwidth=1, relheight=1)
            old_frame.place(relx=curr_old, rely=0, relwidth=1, relheight=1)

            self.after(dt, lambda: step(i + 1))

        step(0)

    def animate_overlay_open(self, overlay):
        overlay.place(relx=0, rely=1, relwidth=1, relheight=1)
        steps = 15
        dt = 10
        def step(i):
            if i > steps:
                overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                return
            progress = i / steps
            # Move from rely=1 to rely=0
            curr_y = 1.0 - progress
            overlay.place(relx=0, rely=curr_y, relwidth=1, relheight=1)
            self.after(dt, lambda: step(i+1))
        step(0)

    def animate_overlay_close(self, overlay):
        steps = 15
        dt = 10
        def step(i):
            if i > steps:
                overlay.destroy()
                self.settings_overlay = None
                return
            progress = i / steps
            # Move from rely=0 to rely=1
            curr_y = progress
            overlay.place(relx=0, rely=curr_y, relwidth=1, relheight=1)
            self.after(dt, lambda: step(i+1))
        step(0)

    # ---------- SCREENS ----------
    def setup_login_screen(self):
        self.login_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)

        # Center Card
        card = ctk.CTkFrame(self.login_frame, fg_color=BG_SIDEBAR, corner_radius=30, width=400, height=550)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # Logo Area
        logo_area = ctk.CTkFrame(card, fg_color="transparent", height=100)
        logo_area.pack(fill="x", pady=(40, 10))

        try:
            icon = ctk.CTkImage(light_image=Image.open(asset_path(LOGO_FILENAME)), size=(60, 60))
            ctk.CTkLabel(logo_area, text="", image=icon).pack()
        except:
            ctk.CTkLabel(logo_area, text="🧬", font=("Arial", 60)).pack()

        ctk.CTkLabel(card, text="HELIX", font=FONT_HEADER, text_color=HELIX_PURPLE).pack(pady=(0, 30))

        # Inputs
        self.login_mode = True # True = Login, False = Signup

        self.var_email = ctk.StringVar()
        self.var_pass = ctk.StringVar()

        self.entry_auth_email = ctk.CTkEntry(card, textvariable=self.var_email, placeholder_text="Email", height=50, corner_radius=25, fg_color=BG_INPUT, border_width=1, border_color="#333")
        self.entry_auth_email.pack(fill="x", padx=40, pady=10)

        self.entry_auth_pass = ctk.CTkEntry(card, textvariable=self.var_pass, placeholder_text="Password", show="*", height=50, corner_radius=25, fg_color=BG_INPUT, border_width=1, border_color="#333")
        self.entry_auth_pass.pack(fill="x", padx=40, pady=10)

        # Action Button
        self.btn_auth_action = ctk.CTkButton(card, text="Log In", height=50, corner_radius=25, fg_color=HELIX_PURPLE, text_color="black", font=FONT_BOLD, command=self.do_auth_action)
        self.btn_auth_action.pack(fill="x", padx=40, pady=20)

        # Toggle Link
        self.lbl_auth_toggle = ctk.CTkLabel(card, text="Don't have an account? Sign Up", font=FONT_SMALL, text_color=HELIX_PURPLE, cursor="hand2")
        self.lbl_auth_toggle.pack(pady=10)
        self.lbl_auth_toggle.bind("<Button-1>", self.toggle_auth_mode)

    def toggle_auth_mode(self, e):
        self.login_mode = not self.login_mode
        if self.login_mode:
            self.btn_auth_action.configure(text="Log In")
            self.lbl_auth_toggle.configure(text="Don't have an account? Sign Up")
        else:
            self.btn_auth_action.configure(text="Create Account")
            self.lbl_auth_toggle.configure(text="Already have an account? Log In")

    def do_auth_action(self):
        if self.login_mode:
            self.do_login()
        else:
            self.initiate_otp()

    def setup_otp_screen(self):
        self.otp_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)

        center = ctk.CTkFrame(self.otp_frame, fg_color=BG_SIDEBAR, corner_radius=40)
        center.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(center, text="VERIFY", font=FONT_HEADER, text_color=HELIX_PURPLE).pack(pady=30, padx=80)

        self.entry_otp = ctk.CTkEntry(center, placeholder_text="Code", height=60, width=200, corner_radius=30,
                                      font=("Segoe UI", 24), justify="center", fg_color=BG_INPUT, border_width=0)
        self.entry_otp.pack(pady=20)

        ctk.CTkButton(center, text="Submit", height=50, width=200, corner_radius=25, fg_color=HELIX_PURPLE, text_color="black",
                      command=self.verify_otp).pack(pady=20)

        ctk.CTkButton(center, text="Back", height=40, width=200, fg_color="transparent", command=self.show_login).pack(pady=10)

    def setup_main_app(self):
        self.app_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)
        self.app_frame.grid_rowconfigure(0, weight=1)
        self.app_frame.grid_columnconfigure(0, weight=0)
        self.app_frame.grid_columnconfigure(1, weight=1)

        # Sidebar (Talk only)
        self.sidebar = ctk.CTkFrame(self.app_frame, width=280, fg_color=BG_SIDEBAR, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo row
        logo_row = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=80)
        logo_row.pack(fill="x", padx=25, pady=(25, 15))
        try:
            icon = ctk.CTkImage(light_image=Image.open(asset_path(LOGO_FILENAME)), size=(34, 34))
            ctk.CTkLabel(logo_row, text="", image=icon).pack(side="left")
        except Exception:
            pass
        ctk.CTkLabel(logo_row, text="HELIX", font=FONT_HEADER, text_color=TEXT_WHITE).pack(side="left", padx=12)

        # Primary Actions
        action_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        action_row.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(action_row, text="+ Chat", fg_color=BG_CARD, hover_color=BG_INPUT, width=110, height=40, corner_radius=20,
                      font=FONT_BOLD, text_color=TEXT_GRAY, command=self.create_new_chat).pack(side="left", padx=(0, 5))

        ctk.CTkButton(action_row, text="+ Canvas", fg_color=BG_CARD, hover_color=BG_INPUT, width=110, height=40, corner_radius=20,
                      font=FONT_BOLD, text_color=TEXT_GRAY, command=self.notebook_new).pack(side="right", padx=(5, 0))

        # LIBRARY SCROLL
        self.library_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.library_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=60)
        footer.pack(fill="x", side="bottom", padx=20, pady=18)

        self.settings_btn = ctk.CTkButton(
            footer,
            text="⚙️ Settings",
            fg_color="transparent",
            hover_color=BG_CARD,
            anchor="w",
            height=45,
            corner_radius=22,
            font=FONT_NORMAL,
            command=self.open_settings,
        )
        self.settings_btn.pack(fill="x")

        # Main area
        self.main_area = ctk.CTkFrame(self.app_frame, fg_color=BG_DARK)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        # PAGES CONTAINER (Use Place for Animations)
        self.pages_container = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.pages_container.grid(row=0, column=0, sticky="nsew")
        # No grid config needed for children since we use place

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.pages["Talk to AI"] = ctk.CTkFrame(self.pages_container, fg_color=BG_DARK)
        self.pages["Canvas"] = ctk.CTkFrame(self.pages_container, fg_color=BG_DARK)
        self.pages["Messages"] = ctk.CTkFrame(self.pages_container, fg_color=BG_DARK)
        self.pages["Quick Fix"] = ctk.CTkFrame(self.pages_container, fg_color=BG_DARK)

        # Init pages (hidden or placed)
        for p in self.pages.values():
            p.place(relx=1.0, rely=0, relwidth=1, relheight=1) # Start off-screen right

        self._setup_talk_page(self.pages["Talk to AI"])
        self._setup_notebook_page(self.pages["Canvas"])
        self._setup_dm_page(self.pages["Messages"])
        self._setup_quickfix_page(self.pages["Quick Fix"])

        # Bottom nav pill
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        # Make background distinct or darker to avoid visual overlap artifacts
        self.bottom_nav = ctk.CTkFrame(self.main_area, fg_color="#181818", corner_radius=22, height=44)
        self.bottom_nav.place(relx=0.5, rely=1.0, anchor="s", y=-14)

        def make_nav_btn(name: str, w: int = 105):
            b = ctk.CTkButton(
                self.bottom_nav,
                text=name,
                fg_color="transparent",
                hover_color="#333333", # Darker hover to prevent "box" look
                text_color=TEXT_WHITE,
                width=w,
                height=34,
                corner_radius=17,
                font=FONT_SMALL,
                command=lambda n=name: self.switch_tab(n),
            )
            b.pack(side="left", padx=6, pady=5)
            self.nav_buttons[name] = b

        make_nav_btn("Talk to AI", 110)
        make_nav_btn("Canvas", 100)
        make_nav_btn("Messages", 110)
        make_nav_btn("Quick Fix", 100)

        self.widget = FloatingWidget(self)

    # ---------- PAGES ----------
    def _setup_talk_page(self, tab: ctk.CTkFrame):
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=0)
        tab.grid_columnconfigure(0, weight=1)

        # welcome
        self.welcome_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.welcome_frame.grid(row=0, column=0, sticky="nsew")

        center = ctk.CTkFrame(self.welcome_frame, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        try:
            icon = ctk.CTkImage(light_image=Image.open(asset_path(LOGO_FILENAME)), size=(80, 80))
            ctk.CTkLabel(center, text="", image=icon).pack(pady=(0, 20))
        except Exception:
            pass

        ctk.CTkLabel(center, text="How can I help?", font=("Google Sans", 32, "bold"), text_color="white").pack(pady=5)

        # Suggestions grid
        sugg_frame = ctk.CTkFrame(center, fg_color="transparent")
        sugg_frame.pack(pady=30)

        suggestions = [
            ("Draft an email", "to my boss about a raise"),
            ("Debug code", "in my python script"),
            ("Plan a trip", "to Kyoto in the spring"),
            ("Brainstorm", "marketing ideas for a coffee shop")
        ]

        for i, (head, sub) in enumerate(suggestions):
            btn = ctk.CTkButton(
                sugg_frame,
                text=f"{head}\n{sub}",
                font=FONT_NORMAL,
                fg_color=BG_CARD,
                hover_color=BG_INPUT,
                width=160,
                height=80,
                corner_radius=15,
                anchor="nw",
                command=lambda t=f"{head} {sub}": self.chat_entry_insert(t)
            )
            # Simple grid layout for suggestions 2x2
            r, c = divmod(i, 2)
            btn.grid(row=r, column=c, padx=8, pady=8)

        # chat scroll (hidden until messages)
        self.chat_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.chat_scroll.grid(row=0, column=0, sticky="nsew", padx=120, pady=(40, 120))
        self.chat_scroll.grid_columnconfigure(0, weight=1)
        self.chat_scroll.grid_remove()

        self.chat_rows: list[BubbleMessage] = []
        self.chat_row_index = 0

        # input island
        input_wrapper = ctk.CTkFrame(tab, fg_color="transparent")
        input_wrapper.grid(row=1, column=0, sticky="ew", padx=120, pady=(0, 90))  # leave room for bottom nav

        self.input_pill = ctk.CTkFrame(input_wrapper, fg_color=BG_INPUT, height=120, corner_radius=32)
        self.input_pill.pack(fill="x", expand=True)

        self.chat_entry = ctk.CTkTextbox(self.input_pill, font=FONT_INPUT, height=50, fg_color="transparent",
                                         text_color=TEXT_WHITE, wrap="word", activate_scrollbars=False)
        self.chat_entry.pack(fill="x", padx=20, pady=(15, 5))
        self.setup_textbox_placeholder(self.chat_entry, "Ask Helix anything...", self.send_chat)

        tools_row = ctk.CTkFrame(self.input_pill, fg_color="transparent", height=40)
        tools_row.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_attach = ctk.CTkButton(
            tools_row, text="+", width=35, height=35,
            fg_color=BG_CARD, hover_color=BG_DARK,
            text_color=TEXT_GRAY, font=("Arial", 20),
            corner_radius=17, command=self.toggle_attach
        )
        self.btn_attach.pack(side="left", padx=(10, 5))

        self.model_var = ctk.StringVar(value="Standard")
        self.model_dropdown = ctk.CTkOptionMenu(
            tools_row,
            variable=self.model_var,
            values=["Standard", "Thinking"],
            command=self.change_model,
            width=120,
            height=32,
            corner_radius=16,
            fg_color=BG_CARD,
            button_color=BG_CARD,
            button_hover_color=BG_DARK,
            text_color=TEXT_GRAY,
        )
        self.model_dropdown.pack(side="left", padx=5)

        self.btn_send = ctk.CTkButton(
            tools_row, text="➤",
            width=50, height=35,
            fg_color=HELIX_PURPLE, hover_color=HELIX_HOVER,
            text_color="black", corner_radius=17,
            font=("Arial", 16), command=self.send_chat
        )
        self.btn_send.pack(side="right", padx=10)

        # adjust wraplength dynamically on resize
        def on_resize(_):
            max_w = max(420, min(780, tab.winfo_width() - 240))
            for msg in self.chat_rows:
                msg.set_wraplength(max_w)

        tab.bind("<Configure>", on_resize)

    def _setup_notebook_page(self, tab: ctk.CTkFrame):
        # Two views: Dashboard (List) and Editor (Content)
        # We'll use a container and switch visibility
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.canvas_container = ctk.CTkFrame(tab, fg_color="transparent")
        self.canvas_container.grid(row=0, column=0, sticky="nsew")
        self.canvas_container.grid_columnconfigure(0, weight=1)
        self.canvas_container.grid_rowconfigure(0, weight=1)

        # 1. DASHBOARD VIEW
        self.canvas_dashboard = ctk.CTkFrame(self.canvas_container, fg_color=BG_DARK)
        self.canvas_dashboard.grid(row=0, column=0, sticky="nsew")

        # Dashboard Header
        db_head = ctk.CTkFrame(self.canvas_dashboard, fg_color="transparent")
        db_head.pack(fill="x", padx=40, pady=40)

        ctk.CTkLabel(db_head, text="Canvas", font=FONT_HEADER, text_color="white").pack(side="left")
        ctk.CTkButton(db_head, text="+ New Notebook", width=140, height=40, corner_radius=20,
                      fg_color=HELIX_PURPLE, text_color="black", font=FONT_BOLD,
                      command=self.notebook_new).pack(side="right")

        # Notebook Grid/List
        self.canvas_list_scroll = ctk.CTkScrollableFrame(self.canvas_dashboard, fg_color="transparent")
        self.canvas_list_scroll.pack(fill="both", expand=True, padx=40, pady=(0, 100)) # Pad for bottom nav

        # 2. EDITOR VIEW
        self.canvas_editor = ctk.CTkFrame(self.canvas_container, fg_color=BG_DARK)
        self.canvas_editor.grid(row=0, column=0, sticky="nsew")
        self.canvas_editor.grid_remove() # Start hidden

        self.canvas_editor.grid_columnconfigure(0, weight=1)
        self.canvas_editor.grid_rowconfigure(1, weight=1) # Text area

        # Editor Toolbar (Back btn + Title + Save)
        ed_toolbar = ctk.CTkFrame(self.canvas_editor, fg_color="transparent", height=60)
        ed_toolbar.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 5))

        ctk.CTkButton(ed_toolbar, text="← Home", width=80, height=35, fg_color="transparent", border_width=1, border_color="#333", command=self.canvas_back_to_home).pack(side="left", padx=10)

        self.note_title = ctk.CTkEntry(ed_toolbar, font=("Google Sans", 20, "bold"), fg_color="transparent", border_width=0, placeholder_text="Untitled Canvas", width=400)
        self.note_title.pack(side="left", padx=20)

        ctk.CTkButton(ed_toolbar, text="Save", width=70, height=35, corner_radius=17, fg_color=BG_CARD, hover_color=BG_DARK, command=self.notebook_save).pack(side="right", padx=5)
        ctk.CTkButton(ed_toolbar, text="Draft Mode", width=100, height=35, corner_radius=17, fg_color=BG_CARD, hover_color=BG_DARK, command=self.open_canvas_drafting).pack(side="right", padx=5)

        # Editor Frame
        editor_frame = ctk.CTkFrame(self.canvas_editor, fg_color=BG_INPUT, corner_radius=20)
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 90)) # Padding for nav

        self.notebook = ctk.CTkTextbox(editor_frame, font=FONT_NORMAL, fg_color="transparent", wrap="word", height=400)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=20)

        # AI Bar (inside editor frame at bottom)
        ai_bar = ctk.CTkFrame(editor_frame, fg_color=BG_CARD, height=60, corner_radius=30)
        ai_bar.pack(fill="x", padx=20, pady=20)

        self.note_prompt = ctk.CTkTextbox(ai_bar, height=35, fg_color="transparent", font=FONT_INPUT, wrap="word")
        self.note_prompt.pack(side="left", fill="x", expand=True, padx=20, pady=12)
        self.setup_textbox_placeholder(self.note_prompt, "Quick edit...", self.notebook_ai_run)

        ctk.CTkButton(ai_bar, text="Run", width=60, height=40, corner_radius=20, fg_color=HELIX_PURPLE, text_color="black",
                      command=self.notebook_ai_run).pack(side="right", padx=10)

        self.canvas_overlay = None
        self.show_canvas_dashboard() # Default state

    def show_canvas_dashboard(self):
        self.canvas_editor.grid_remove()
        self.canvas_dashboard.grid()
        self.refresh_canvas_list_ui()

    def show_canvas_editor(self):
        self.canvas_dashboard.grid_remove()
        self.canvas_editor.grid()

    def canvas_back_to_home(self):
        self.notebook_save() # Auto-save
        self.show_canvas_dashboard()

    def refresh_canvas_list_ui(self):
        for w in self.canvas_list_scroll.winfo_children(): w.destroy()
        if not self.current_user: return

        notes = db.load_notebooks_list(self.current_user)
        if not notes:
             ctk.CTkLabel(self.canvas_list_scroll, text="No notebooks created yet.", font=FONT_NORMAL, text_color="gray").pack(pady=40)
             return

        # Grid layout for cards (e.g. 3 columns)
        # ctkScrollableFrame uses pack/grid internally. We'll use a grid inside it.
        container = ctk.CTkFrame(self.canvas_list_scroll, fg_color="transparent")
        container.pack(fill="both", expand=True)

        columns = 3
        for i, (nid, title) in enumerate(notes):
            row = i // columns
            col = i % columns

            card = ctk.CTkButton(
                container,
                text=f"\n\n{title or 'Untitled'}",
                font=FONT_BOLD,
                fg_color=BG_CARD,
                hover_color=BG_INPUT,
                width=200,
                height=150,
                corner_radius=15,
                anchor="sw",
                command=lambda x=nid: self.load_notebook(x)
            )
            card.grid(row=row, column=col, padx=15, pady=15)

    def open_canvas_drafting(self):
        if self.canvas_overlay: return
        self.canvas_overlay = CanvasDraftingOverlay(self.pages["Canvas"], self, self.notebook.get("0.0", "end").strip())
        self.animate_overlay_open(self.canvas_overlay)

    def _setup_dm_page(self, tab: ctk.CTkFrame):
        tab.grid_columnconfigure(0, weight=0) # Thread list
        tab.grid_columnconfigure(1, weight=1) # Chat area
        tab.grid_columnconfigure(2, weight=0) # Draft panel (toggleable)
        tab.grid_rowconfigure(0, weight=1)

        # LEFT: Thread List (Friends)
        self.dm_list = ctk.CTkFrame(tab, width=260, fg_color=BG_SIDEBAR, corner_radius=0)
        self.dm_list.grid(row=0, column=0, sticky="nsew")
        self.dm_list.grid_propagate(False)

        # Header: Avatar + Add Friend
        self.dm_header = ctk.CTkFrame(self.dm_list, fg_color="transparent", height=60)
        self.dm_header.pack(fill="x", padx=15, pady=20)

        # Avatar (Loaded later in show_app)
        self.dm_avatar_lbl = ctk.CTkLabel(self.dm_header, text="")
        self.dm_avatar_lbl.pack(side="left")

        # Add Friend Button
        ctk.CTkButton(
            self.dm_header,
            text="+",
            width=35,
            height=35,
            corner_radius=17,
            fg_color=BG_CARD,
            hover_color=BG_INPUT,
            text_color="white",
            font=("Arial", 20),
            command=self.dm_add_friend_dialog
        ).pack(side="right")

        # Initial empty state
        self.draw_fallback_avatar(self.dm_header)

        # Init right side
        self._init_dm_right_side(tab)

    def refresh_dm_header(self):
        # Clear old avatar widget content if any
        for w in self.dm_header.winfo_children():
            if isinstance(w, ctk.CTkLabel) or isinstance(w, ctk.CTkCanvas):
                w.destroy()

        # Re-add Avatar
        if self.current_user:
            try:
                _, _, _, my_av_path = db.get_profile(self.current_user)
                if my_av_path and os.path.exists(my_av_path):
                     try:
                         pil_img = Image.open(my_av_path)
                         # Deferred loading/error check
                         av_img = ctk.CTkImage(light_image=make_circle(pil_img), size=(40, 40))
                         lbl = ctk.CTkLabel(self.dm_header, text="", image=av_img)
                         lbl.pack(side="left")
                     except Exception:
                         self.draw_fallback_avatar(self.dm_header)
                else:
                     self.draw_fallback_avatar(self.dm_header)
            except Exception:
                self.draw_fallback_avatar(self.dm_header)
        else:
            self.draw_fallback_avatar(self.dm_header)

        # Re-add Button (since we cleared children)
        ctk.CTkButton(
            self.dm_header,
            text="+",
            width=35,
            height=35,
            corner_radius=17,
            fg_color=BG_CARD,
            hover_color=BG_INPUT,
            text_color="white",
            font=("Arial", 20),
            command=self.dm_add_friend_dialog
        ).pack(side="right")

    def draw_fallback_avatar(self, parent):
        avatar_canvas = ctk.CTkCanvas(parent, width=40, height=40, bg=BG_SIDEBAR, highlightthickness=0)
        avatar_canvas.pack(side="left")
        avatar_canvas.create_oval(2, 2, 38, 38, fill=HELIX_PURPLE, outline="")
        avatar_canvas.create_text(20, 20, text="ME", fill="black", font=("Arial", 10, "bold"))

    def _init_dm_right_side(self, tab):
        ctk.CTkLabel(self.dm_list, text="Messages", font=FONT_BOLD, text_color=TEXT_GRAY).pack(anchor="w", padx=20, pady=(10, 5))

        self.dm_scroll = ctk.CTkScrollableFrame(self.dm_list, fg_color="transparent")
        self.dm_scroll.pack(fill="both", expand=True)

        # CENTER: Chat
        self.dm_chat_area = ctk.CTkFrame(tab, fg_color=BG_DARK, corner_radius=0)
        self.dm_chat_area.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.dm_chat_area.grid_rowconfigure(0, weight=1)
        self.dm_chat_area.grid_columnconfigure(0, weight=1)

        self.dm_msgs_scroll = ctk.CTkScrollableFrame(self.dm_chat_area, fg_color="transparent")
        self.dm_msgs_scroll.grid(row=0, column=0, sticky="nsew", pady=(20, 10), padx=20)

        # Input Area (with padding for bottom nav)
        dm_input_area = ctk.CTkFrame(self.dm_chat_area, fg_color="transparent")
        dm_input_area.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 90)) # 90px padding for bottom nav

        self.dm_input = ctk.CTkTextbox(dm_input_area, height=50, font=FONT_NORMAL, fg_color=BG_INPUT, border_width=0, corner_radius=25)
        self.dm_input.pack(fill="x", pady=(0, 10))
        self.setup_textbox_placeholder(self.dm_input, "Message...", self.dm_send)

        btn_row = ctk.CTkFrame(dm_input_area, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(btn_row, text="Draft with AI ✨", width=120, height=30, fg_color=BG_CARD, corner_radius=15, command=self.dm_toggle_draft).pack(side="left")
        ctk.CTkButton(btn_row, text="Send", width=80, height=30, fg_color=HELIX_PURPLE, text_color="black", corner_radius=15, command=self.dm_send).pack(side="right")

        # RIGHT: Draft Panel (Hidden by default)
        self.dm_draft_panel = ctk.CTkFrame(tab, width=250, fg_color=BG_SIDEBAR, corner_radius=0)
        # Grid it later when toggled

        self.dm_current_contact = None
        self.dm_draft_visible = False

    def dm_add_friend_dialog(self):
        dialog = ctk.CTkInputDialog(text="Enter friend's email:", title="Add Friend")
        email = dialog.get_input()
        if email:
            ok, msg = db.send_friend_request(self.current_user, email)
            messagebox.showinfo("Result", msg)
            self.dm_refresh_list()

    def dm_refresh_list(self):
        for w in self.dm_scroll.winfo_children(): w.destroy()

        # Pending Requests
        pending = db.get_pending_requests(self.current_user)
        if pending:
             ctk.CTkLabel(self.dm_scroll, text="Pending Requests", font=("Arial", 12, "bold"), text_color=HELIX_PURPLE).pack(anchor="w", padx=10, pady=(10, 5))
             for req in pending:
                 # req = {id, email, name}
                 frame = ctk.CTkFrame(self.dm_scroll, fg_color=BG_CARD)
                 frame.pack(fill="x", pady=2, padx=5)

                 ctk.CTkLabel(frame, text=f"{req['name']}", font=FONT_BOLD).pack(anchor="w", padx=10, pady=(5,0))
                 ctk.CTkLabel(frame, text=f"@{req['email'].split('@')[0]}", font=FONT_SMALL, text_color="gray").pack(anchor="w", padx=10)

                 act_row = ctk.CTkFrame(frame, fg_color="transparent")
                 act_row.pack(fill="x", padx=10, pady=5)
                 ctk.CTkButton(act_row, text="Accept", height=24, width=60, fg_color=HELIX_PURPLE, text_color="black",
                               command=lambda rid=req['id']: self.dm_accept_request(rid)).pack(side="left")

        # Get Friends
        friends = db.get_friendships(self.current_user)
        # Also get Contacts (legacy support for DMs started without friendship)
        contacts = db.get_contacts(self.current_user)

        if friends:
             ctk.CTkLabel(self.dm_scroll, text="Friends", font=FONT_BOLD).pack(anchor="w", padx=10, pady=(10, 5))

        if not friends and not contacts and not pending:
             ctk.CTkLabel(self.dm_scroll, text="No friends yet.", text_color="gray").pack(pady=20)

        for f in friends:
             # f = {email, name, avatar, status}
             btn = ctk.CTkButton(
                 self.dm_scroll,
                 text=f"👤 {f['name']}\n@{f['email'].split('@')[0]}",
                 height=60,
                 fg_color="transparent",
                 hover_color=BG_CARD,
                 anchor="w",
                 command=lambda e=f['email']: self.dm_start_chat_with_email(e)
             )
             btn.pack(fill="x", pady=2)

        # Separator for legacy/manual contacts if any
        if contacts:
             ctk.CTkLabel(self.dm_scroll, text="Recent", font=FONT_BOLD).pack(anchor="w", padx=10, pady=10)
             for cid, name, last in contacts:
                btn = ctk.CTkButton(
                    self.dm_scroll,
                    text=f"{name}\n{last[:20]}...",
                    height=50,
                    fg_color="transparent",
                    anchor="w",
                    command=lambda x=cid: self.dm_load_thread(x)
                )
                btn.pack(fill="x", pady=2)

    def dm_accept_request(self, rid):
        db.accept_friend_request(rid)
        self.dm_refresh_list()

    def dm_start_chat_with_email(self, target_email):
        # Find existing contact ID or create new
        # Simplified: Loop through contacts to find one with this email
        # Ideally schema would link contact -> user_email
        # For now, create a new contact stub
        name = target_email.split("@")[0]
        cid = db.add_contact(self.current_user, name) # Duplicate check missing for brevity
        self.dm_load_thread(cid)

    def dm_load_thread(self, contact_id):
        self.dm_current_contact = contact_id
        for w in self.dm_msgs_scroll.winfo_children(): w.destroy()
        msgs = db.get_dm_messages(contact_id)
        for role, content, is_draft in msgs:
            align = "e" if role == "me" else "w"
            color = HELIX_PURPLE if role == "me" else BG_CARD
            lbl = ctk.CTkLabel(self.dm_msgs_scroll, text=content, fg_color=color, corner_radius=10, padx=10, pady=5, wraplength=400)
            lbl.pack(anchor=align, pady=5, padx=10)

    def dm_send(self):
        txt = self.dm_input.get("0.0", "end").strip()
        if not txt or not self.dm_current_contact: return
        db.save_dm_message(self.dm_current_contact, "me", txt)
        self.dm_input.delete("0.0", "end")
        self.dm_load_thread(self.dm_current_contact)
        # Simulate reply
        self.after(1000, lambda: self.dm_receive_sim(self.dm_current_contact))

    def dm_receive_sim(self, cid):
        db.save_dm_message(cid, "them", "This is a simulated reply.")
        if self.dm_current_contact == cid: self.dm_load_thread(cid)

    def dm_toggle_draft(self):
        self.dm_draft_visible = not self.dm_draft_visible
        if self.dm_draft_visible:
            self.dm_draft_panel.grid(row=0, column=2, sticky="nsew")
            # Populate draft panel content
            for w in self.dm_draft_panel.winfo_children(): w.destroy()
            ctk.CTkLabel(self.dm_draft_panel, text="AI Draft Assist", font=FONT_BOLD).pack(pady=20)
            self.draft_prompt = ctk.CTkTextbox(self.dm_draft_panel, height=80, fg_color=BG_INPUT)
            self.draft_prompt.pack(padx=10, fill="x")
            self.draft_prompt.insert("0.0", "Draft a reply that...")

            ctk.CTkButton(self.dm_draft_panel, text="Generate", command=self.dm_run_draft).pack(pady=10)
            self.draft_result = ctk.CTkTextbox(self.dm_draft_panel, height=200, fg_color=BG_INPUT)
            self.draft_result.pack(padx=10, fill="both", expand=True)
            ctk.CTkButton(self.dm_draft_panel, text="Use Draft", fg_color=HELIX_PURPLE, text_color="black", command=self.dm_use_draft).pack(pady=20)
        else:
            self.dm_draft_panel.grid_forget()

    def dm_run_draft(self):
        p = self.draft_prompt.get("0.0", "end")
        # Stub AI gen
        self.draft_result.insert("end", f"\n[Draft based on: {p.strip()}]\nHello! I wanted to check in...")

    def dm_use_draft(self):
        txt = self.draft_result.get("0.0", "end").strip()
        self.dm_input.insert("end", txt)
        self.dm_toggle_draft()

    def _setup_quickfix_page(self, tab: ctk.CTkFrame):
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)

        self.q_result = ctk.CTkTextbox(tab, font=FONT_NORMAL, fg_color=BG_INPUT, corner_radius=20, wrap="word")
        self.q_result.grid(row=0, column=0, sticky="nsew", padx=60, pady=(60, 10))

        bar = ctk.CTkFrame(tab, fg_color=BG_INPUT, height=70, corner_radius=35)
        bar.grid(row=1, column=0, sticky="ew", padx=60, pady=(0, 90))  # bottom padding for nav

        self.q_prompt = ctk.CTkTextbox(bar, height=45, fg_color="transparent", font=FONT_INPUT, wrap="word")
        self.q_prompt.pack(side="left", fill="x", expand=True, padx=25, pady=12)
        self.setup_textbox_placeholder(self.q_prompt, "Custom instruction...", self.quick_fix_custom_run)

        ctk.CTkButton(bar, text="Refine", width=100, height=45, corner_radius=22, fg_color=HELIX_PURPLE, text_color="black",
                      command=self.quick_fix_custom_run).pack(side="right", padx=12)

    # ---------- TAB / NAV ----------
    def chat_entry_insert(self, text):
        self.chat_entry.delete("0.0", "end")
        self.chat_entry.insert("0.0", text)
        self.chat_entry.configure(text_color=TEXT_WHITE)
        self.chat_entry.has_placeholder = False
        self.chat_entry.focus_force()

    def switch_tab(self, tab_name: str):
        if tab_name == self.active_tab: return
        if self.is_animating: return

        # Decide direction
        order = ["Talk to AI", "Canvas", "Messages", "Quick Fix"]
        try:
            curr_idx = order.index(self.active_tab)
            new_idx = order.index(tab_name)
            direction = "right" if new_idx > curr_idx else "left"
        except:
            direction = "right"

        old_frame = self.pages[self.active_tab]
        new_frame = self.pages[tab_name]

        self.active_tab = tab_name
        self.animate_slide_page(old_frame, new_frame, direction)

        # Sidebar visible ONLY on Talk to AI
        if tab_name == "Talk to AI":
            self.sidebar.grid()
        else:
            self.sidebar.grid_remove()

        for name, btn in self.nav_buttons.items():
            btn.configure(fg_color=BG_INPUT if name == tab_name else "transparent")

        # Ensure bottom nav stays on top
        self.bottom_nav.lift()

    # ---------- SETTINGS ----------
    def open_settings(self):
        if not self.current_user: return
        if self.settings_overlay: return # Already open

        # Pass self (HelixApp) as parent, but place it inside app_frame or main_area
        # To make it cover everything, we use self (the root window) or app_frame.
        # But SettingsOverlay expects 'parent_app' to be the logic controller (HelixApp)
        # AND a parent widget.

        # We will make SettingsOverlay a child of app_frame so it stays in the content area
        self.settings_overlay = SettingsOverlay(self.app_frame, self, db, self.current_user, self.do_logout)
        self.animate_overlay_open(self.settings_overlay)

    # ---------- AUTH ----------
    def show_login(self):
        self.app_frame.pack_forget()
        self.otp_frame.pack_forget()
        self.login_frame.pack(fill="both", expand=True)

    def show_otp(self):
        self.login_frame.pack_forget()
        self.otp_frame.pack(fill="both", expand=True)

    def show_app(self):
        self.login_frame.pack_forget()
        self.otp_frame.pack_forget()
        self.app_frame.pack(fill="both", expand=True)

        self.saved_chats = db.load_chats(self.current_user)
        self.refresh_notebook_list()

        cleaned = {}
        for cid, cdata in (self.saved_chats or {}).items():
            if not isinstance(cdata, dict):
                continue
            title = str(cdata.get("title", "New Chat"))
            msgs = cdata.get("msgs", [])
            if not isinstance(msgs, list):
                msgs = []
            cleaned[cid] = {"title": title, "msgs": msgs}
        self.saved_chats = cleaned

        self.refresh_sidebar()
        if hasattr(self, "refresh_dm_header"):
             self.refresh_dm_header()
        self.create_new_chat()

        # Reset pages
        for p in self.pages.values(): p.place(relx=1.0, rely=0)
        self.pages["Talk to AI"].place(relx=0, rely=0)
        self.active_tab = "Talk to AI"
        self.switch_tab("Talk to AI") # ensures UI state correct

    def do_login(self):
        email = self.var_email.get().strip()
        p = self.var_pass.get()

        if not email or not p:
            messagebox.showerror("Error", "Missing email or password.")
            return

        success, tokens = db.login(email, p)
        if success:
            self.current_user = email
            self.token_balance = tokens
            save_session(email)
            self.show_app()
        else:
            messagebox.showerror("Error", "Login failed.")

    def do_logout(self):
        clear_session()
        self.current_user = None
        self.token_balance = 0
        self.saved_chats = {}
        self.current_chat_id = None
        self.clear_chat_view()
        self.show_login()

    def initiate_otp(self):
        self.pending_email = self.var_email.get().strip()
        self.pending_pass = self.var_pass.get()

        if not self.pending_email or not self.pending_pass:
            messagebox.showerror("Error", "Missing email or password.")
            return
        if db.check_exists(self.pending_email):
            messagebox.showerror("Error", "Account already exists.")
            return

        self.pending_otp = str(random.randint(100000, 999999))

        def send():
            try:
                # In production, this should handle network errors robustly
                # If smtp fails, we might just print code to console for debugging
                success, msg = send_otp_email(self.pending_email, self.pending_otp)
                if not success:
                    print(f"DEBUG: Email failed. Code is {self.pending_otp}")
            except Exception as e:
                print(f"DEBUG: Email crash. Code is {self.pending_otp}. Error: {e}")

        threading.Thread(target=send, daemon=True).start()
        self.entry_otp.delete(0, "end")
        self.show_otp()

    def verify_otp(self):
        code = self.entry_otp.get().strip()
        if not code or code != self.pending_otp:
            messagebox.showerror("Error", "Invalid code.")
            return

        ok, msg = db.register_final(self.pending_email, self.pending_pass)
        if not ok:
            messagebox.showerror("Error", msg)
            return

        self.current_user = self.pending_email
        self.token_balance = INITIAL_TOKENS
        save_session(self.current_user)
        self.show_app()

    # ---------- SIDEBAR / LIBRARY ----------
    def refresh_sidebar(self):
        for w in self.library_scroll.winfo_children():
            w.destroy()

        # CHATS SECTION
        ctk.CTkLabel(self.library_scroll, text="CHATS", font=("Google Sans", 11, "bold"), text_color="#555").pack(anchor="w", padx=15, pady=(10, 5))

        ids = list(self.saved_chats.keys())[::-1]
        for c_id in ids:
            title = self.saved_chats[c_id].get("title", "New Chat")
            title = str(title).strip() or "New Chat"
            display = title if len(title) <= 24 else title[:24] + "…"

            btn = ctk.CTkButton(
                self.library_scroll,
                text="💬 " + display,
                anchor="w",
                fg_color="transparent",
                hover_color=BG_CARD,
                height=35,
                corner_radius=8,
                font=FONT_NORMAL,
                text_color="#CCC",
                command=lambda x=c_id: self.load_chat(x),
            )
            btn.pack(fill="x", pady=1, padx=6)
            btn.bind("<Button-3>", lambda e, cid=c_id: self.show_chat_context_menu(e, cid))

        # CANVAS SECTION
        ctk.CTkLabel(self.library_scroll, text="CANVASES", font=("Google Sans", 11, "bold"), text_color="#555").pack(anchor="w", padx=15, pady=(20, 5))

        if self.current_user:
            notebooks = db.load_notebooks_list(self.current_user)
            for nid, title in notebooks:
                display = title or "Untitled"
                btn = ctk.CTkButton(
                    self.library_scroll,
                    text="📝 " + display,
                    anchor="w",
                    fg_color="transparent",
                    hover_color=BG_CARD,
                    height=35,
                    corner_radius=8,
                    font=FONT_NORMAL,
                    text_color="#CCC",
                    command=lambda x=nid: self.load_notebook(x),
                )
                btn.pack(fill="x", pady=1, padx=6)

    def show_chat_context_menu(self, event, chat_id: str):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Open", command=lambda: self.load_chat(chat_id))
        menu.add_command(label="Branch (duplicate)", command=lambda: self.branch_chat(chat_id))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self.delete_chat(chat_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def delete_chat(self, chat_id: str):
        if chat_id not in self.saved_chats:
            return
        if not messagebox.askyesno("Delete chat", "Delete this chat?"):
            return
        del self.saved_chats[chat_id]
        if self.current_chat_id == chat_id:
            self.create_new_chat()
        self.save_history()
        self.refresh_sidebar()

    def branch_chat(self, chat_id: str):
        if chat_id not in self.saved_chats:
            return
        src = self.saved_chats[chat_id]
        new_id = str(uuid.uuid4())
        new_title = f"Branch: {src.get('title', 'Chat')}"
        new_msgs = list(src.get("msgs", []))
        self.saved_chats[new_id] = {"title": new_title, "msgs": new_msgs}
        self.save_history()
        self.refresh_sidebar()

    # ---------- CHAT VIEW ----------
    def clear_chat_view(self):
        if hasattr(self, "chat_scroll"):
            for w in self.chat_scroll.winfo_children():
                w.destroy()
        self.chat_rows = []
        self.chat_row_index = 0
        if hasattr(self, "chat_scroll"):
            self.chat_scroll.grid_remove()
        if hasattr(self, "welcome_frame"):
            self.welcome_frame.grid()

    def _ensure_chat_visible(self):
        self.welcome_frame.grid_remove()
        self.chat_scroll.grid()
        self.scroll_chat_to_bottom()

    def add_message(self, role: str, text: str) -> BubbleMessage:
        self._ensure_chat_visible()
        tab = self.pages["Talk to AI"]
        max_w = max(420, min(780, tab.winfo_width() - 240))
        msg = BubbleMessage(self.chat_scroll, role=role, text=text, max_width_px=max_w).grid(self.chat_row_index)
        self.chat_row_index += 1
        self.chat_rows.append(msg)
        self.scroll_chat_to_bottom()
        return msg

    def load_chat(self, chat_id: str):
        self.current_chat_id = chat_id
        self.clear_chat_view()
        data = self.saved_chats.get(chat_id, {"title": "New Chat", "msgs": []})
        msgs = data.get("msgs", [])
        if msgs:
            self._ensure_chat_visible()
        for m in msgs:
            role = "user" if m.get("role") == "user" else "assistant"
            self.add_message(role, str(m.get("content", "")))

    def create_new_chat(self):
        new_id = str(uuid.uuid4())
        self.saved_chats[new_id] = {"title": "New Chat", "msgs": []}
        self.current_chat_id = new_id
        self.clear_chat_view()
        self.save_history()
        self.refresh_sidebar()

    # ---------- NOTEBOOK ----------
    def notebook_new(self):
        self.current_note_id = str(uuid.uuid4())
        self.note_title.delete(0, "end")
        self.note_title.insert(0, "Untitled")
        self.notebook.delete("0.0", "end")
        # Go to Editor Mode
        self.show_canvas_editor()
        self.refresh_sidebar()

    def notebook_save(self):
        if not self.current_note_id:
            self.current_note_id = str(uuid.uuid4())
        db.save_notebook(self.current_note_id, self.current_user, self.note_title.get().strip() or "Untitled",
                         self.notebook.get("0.0", "end").strip())
        self.refresh_notebook_list()
        self.refresh_sidebar()

    def refresh_notebook_list(self):
        # Called when dashboard needs update
        if hasattr(self, "canvas_list_scroll"):
             self.refresh_canvas_list_ui()

    def load_notebook(self, nid: str):
        self.current_note_id = nid
        t, c = db.load_notebook_content(nid)
        self.note_title.delete(0, "end")
        self.note_title.insert(0, t)
        self.notebook.delete("0.0", "end")
        self.notebook.insert("0.0", c)
        self.show_canvas_editor()

    # ---------- QUICK FIX ----------
    def start_quick_fix(self, text: str):
        self.switch_tab("Quick Fix")
        self.q_result.delete("0.0", "end")
        threading.Thread(
            target=self.run_ai_stream,
            args=([{"role": "system", "content": PROMPTS["Fix"]}, {"role": "user", "content": text}], self.q_result, False),
            daemon=True,
        ).start()

    def quick_fix_custom_run(self):
        instruction = self.q_prompt.get("0.0", "end").strip()
        if not instruction or getattr(self.q_prompt, "has_placeholder", False):
            return
        current = self.q_result.get("0.0", "end").strip()
        if not current:
            return
        self.q_prompt.delete("0.0", "end")
        self.setup_textbox_placeholder(self.q_prompt, "Custom instruction...", self.quick_fix_custom_run)

        threading.Thread(
            target=self.run_ai_stream,
            args=(
                [{"role": "system", "content": f"Editor. Instruction: {instruction}"}, {"role": "user", "content": current}],
                self.q_result,
                False,
            ),
            daemon=True,
        ).start()

    # ---------- MODEL / ATTACH ----------
    def toggle_attach(self):
        self.attach_notebook_to_chat = not self.attach_notebook_to_chat
        self.btn_attach.configure(
            fg_color=HELIX_PURPLE if self.attach_notebook_to_chat else BG_CARD,
            text_color="black" if self.attach_notebook_to_chat else TEXT_GRAY
        )

    def change_model(self, v):
        self.current_model_key = v

    # ---------- PROMPTS ----------
    def get_system_prompt(self, key: str) -> str:
        base = PROMPTS.get(key, "")
        try:
            mems = db.get_memories(self.current_user)
            if mems:
                base += "\nMemories:\n" + "\n".join([m[1] for m in mems])
        except Exception:
            pass

        if self.attach_notebook_to_chat and self.current_note_id:
            try:
                base += f"\nNotebook:\n{db.load_notebook_content(self.current_note_id)[1]}"
            except Exception:
                pass

        # RAG Implementation
        if self.use_notebook_context:
            try:
                # Naive Retrieval: Fetch all notes and match keywords
                # In production, use vector embeddings (e.g. chromadb)
                notes = db.load_notebooks_list(self.current_user)
                relevant_text = []
                # prompt isn't passed here, but we can't easily get it without refactoring.
                # Heuristic: Just dump recently modified notes if context is on.
                # A better approach requires passing the prompt to this function.
                # Let's limit to top 3 recent notes for context window safety.
                for nid, title in notes[:3]:
                    _, content = db.load_notebook_content(nid)
                    if content.strip():
                        relevant_text.append(f"--- Note: {title} ---\n{content[:500]}...") # Truncate

                if relevant_text:
                    base += "\n\n[Context from Notebooks]:\n" + "\n".join(relevant_text)
            except Exception:
                pass

        return base

    # ---------- CHAT SEND ----------
    def send_chat(self, text: str | None = None):
        msg = text if text is not None else self.chat_entry.get("0.0", "end").strip()
        if not msg or getattr(self.chat_entry, "has_placeholder", False):
            return

        if not self.current_chat_id:
            self.create_new_chat()

        self.chat_entry.delete("0.0", "end")
        self.setup_textbox_placeholder(self.chat_entry, "Ask Helix anything...", self.send_chat)

        self.add_message("user", msg)
        self.saved_chats[self.current_chat_id]["msgs"].append({"role": "user", "content": msg})

        if len(self.saved_chats[self.current_chat_id]["msgs"]) == 1:
            self._auto_title_chat(self.current_chat_id, msg)

        self.save_history()

        assistant_widget = self.add_message("assistant", "")

        threading.Thread(
            target=self.run_ai_stream,
            args=([{"role": "system", "content": self.get_system_prompt("Chat")}, {"role": "user", "content": msg}], assistant_widget, True),
            daemon=True,
        ).start()

    def _auto_title_chat(self, chat_id: str, first_prompt: str):
        def heuristic_title(text: str) -> str:
            t = " ".join(text.strip().split())
            if not t:
                return "New Chat"
            if len(t) <= 42:
                return t
            return t[:42].rstrip() + "…"

        def generate():
            title = None
            try:
                resp = client.chat.completions.create(
                    model=MODEL_CONFIG["Standard"]["id"],
                    messages=[
                        {"role": "system", "content": "Create a short chat title (2-5 words). Output ONLY the title."},
                        {"role": "user", "content": first_prompt},
                    ],
                    temperature=0.2,
                    stream=False,
                    max_tokens=24,
                )
                title = (resp.choices[0].message.content or "").strip().strip('"')
            except Exception:
                title = None

            if not title:
                title = heuristic_title(first_prompt)

            def apply():
                if chat_id in self.saved_chats:
                    self.saved_chats[chat_id]["title"] = title
                    self.save_history()
                    self.refresh_sidebar()

            self.after(0, apply)

        threading.Thread(target=generate, daemon=True).start()

    # ---------- AI STREAM ----------
    def run_ai_stream(self, msgs, widget, is_chat: bool):
        try:
            # Show Thinking Indicator
            if is_chat and isinstance(widget, BubbleMessage):
                 self.after(0, lambda: widget.set_text("Helix is thinking..."))

            full_response = ""
            first_chunk = True

            stream = client.chat.completions.create(
                model=MODEL_CONFIG[self.current_model_key]["id"],
                messages=msgs,
                temperature=0.7,
                stream=True,
            )
            for chunk in stream:
                if first_chunk:
                    if isinstance(widget, BubbleMessage):
                        self.after(0, lambda: widget.set_text("")) # Clear thinking text
                    else:
                        self.after(0, lambda: widget.delete("0.0", "end"))
                    first_chunk = False

                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    c = delta.content
                    full_response += c
                    if isinstance(widget, BubbleMessage):
                        self.after(0, lambda x=c: (widget.append_text(x), self.scroll_chat_to_bottom()))
                    else:
                        self.after(0, lambda x=c: widget.insert("end", x))

            if is_chat and self.current_chat_id and isinstance(widget, BubbleMessage):
                self.saved_chats[self.current_chat_id]["msgs"].append({"role": "assistant", "content": full_response})
                self.after(0, self.save_history)

            self.after(0, lambda: self.charge_tokens_for_words(full_response))
        except Exception as e:
            if isinstance(widget, BubbleMessage):
                self.after(0, lambda: widget.set_text(f"[Error: {e}]"))
            else:
                self.after(0, lambda: widget.insert("end", f"\n[Error: {e}]"))

    def charge_tokens_for_words(self, text: str):
        c = len(text.split()) * int(MODEL_CONFIG[self.current_model_key]["cost_multiplier"])
        self.token_balance = db.deduct_tokens(self.current_user, c)

    # ---------- NOTEBOOK AI ----------
    def notebook_ai_run(self):
        p = self.note_prompt.get("0.0", "end").strip()
        if not p or getattr(self.note_prompt, "has_placeholder", False):
            return
        self.note_prompt.delete("0.0", "end")
        self.setup_textbox_placeholder(self.note_prompt, "Instruct Helix to edit...", self.notebook_ai_run)

        threading.Thread(
            target=self.run_ai_stream,
            args=(
                [{"role": "system", "content": f"Editor. Inst: {p}"}, {"role": "user", "content": self.notebook.get('0.0', 'end')}],
                self.notebook,
                False,
            ),
            daemon=True,
        ).start()

    # ---------- WIDGET ENTRY ----------
    def show_window(self, mode: str):
        self.deiconify()
        self.attributes("-topmost", True)
        if not self.current_user:
            self.show_login()
            return
        if mode == "clipboard":
            self.start_quick_fix(pyperclip.paste())

    # ---------- PERSIST ----------
    def save_history(self):
        if self.current_user:
            db.save_chats(self.current_user, self.saved_chats)


if __name__ == "__main__":
    # If you pasted secrets into code (tokens/passwords), rotate them and move to env vars.
    app = HelixApp()
    app.mainloop()
