
import customtkinter as ctk
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
from email.message import EmailMessage
from datetime import datetime
from openai import OpenAI
from PIL import Image, ImageDraw, ImageOps
from tkinter import messagebox

# --- CONFIGURATION ---
LOGO_FILENAME = "helix_logo.png"
DB_FILE = "helix_v2.db"
SESSION_FILE = "helix_session.json"

# --- ⚠️ EMAIL SETTINGS ⚠️ ---
SMTP_EMAIL = "your_real_email@gmail.com"
SMTP_PASSWORD = "paste_your_16_digit_app_password_here"

# --- ADMIN SECRETS ---
ADMIN_EMAIL = "admin@helix.com"

# --- MODEL CONFIGURATION ---
MODEL_CONFIG = {
    "Standard": {"id": "hermes-3-llama-3.1-8b", "cost_multiplier": 1, "desc": "⚡"},
    "Thinking": {"id": "glm-4.1v-9b-thinking", "cost_multiplier": 3, "desc": "🧠"}
}

# --- TOKEN ECONOMY ---
INITIAL_TOKENS = 5000

# --- NETWORK SETTINGS ---
LOCAL_URL = "http://localhost:1234/v1"
PUBLIC_URL = "https://balanced-normally-mink.ngrok-free.app/v1"
API_KEY = "lm-studio"

# --- THEME (GEMINI INSPIRED) ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# GEMINI-LIKE PALETTE
BG_DARK = "#131314"  # Deep matte background
BG_SIDEBAR = "#1E1F20"  # Soft Sidebar
BG_CARD = "#28292A"  # Cards/Bubbles
BG_INPUT = "#1E1F20"  # The "Island" input background
HELIX_PURPLE = "#8AB4F8"  # Using a Soft Blue/Purple like the Gemini accent
HELIX_HOVER = "#669DF6"
TEXT_WHITE = "#E3E3E3"
TEXT_GRAY = "#A8A8A8"
PLACEHOLDER_GRAY = "#5f6368"

# TYPOGRAPHY
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


# --- UTILS ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def make_circle(pil_img):
    pil_img = pil_img.convert("RGBA");
    size = pil_img.size
    mask = Image.new('L', size, 0);
    draw = ImageDraw.Draw(mask);
    draw.ellipse((0, 0) + size, fill=255)
    output = ImageOps.fit(pil_img, mask.size, centering=(0.5, 0.5));
    output.putalpha(mask)
    return output


# --- SESSION & EMAIL UTILS ---
def save_session(email):
    try:
        with open(resource_path(SESSION_FILE), "w") as f:
            json.dump({"email": email, "expiry": time.time() + 604800}, f)
    except:
        pass


def load_session():
    try:
        if os.path.exists(resource_path(SESSION_FILE)):
            with open(resource_path(SESSION_FILE)) as f:
                data = json.load(f)
                if data["expiry"] > time.time(): return data["email"]
    except:
        pass
    return None


def clear_session():
    if os.path.exists(resource_path(SESSION_FILE)): os.remove(resource_path(SESSION_FILE))


def send_otp_email(to_email, otp_code):
    try:
        msg = EmailMessage();
        msg.set_content(f"Verification code: {otp_code}");
        msg['Subject'] = 'Helix Code';
        msg['From'] = SMTP_EMAIL;
        msg['To'] = to_email
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465);
        server.login(SMTP_EMAIL, SMTP_PASSWORD);
        server.send_message(msg);
        server.quit()
        return True, "Code sent!"
    except:
        return False, "Email failed."


# --- DATABASE MANAGER ---
class DatabaseManager:
    def __init__(self):
        self.path = resource_path(DB_FILE); self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.path);
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (
                         email
                         TEXT
                         PRIMARY
                         KEY,
                         password_hash
                         BLOB,
                         tokens
                         INTEGER
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS history
                     (
                         email
                         TEXT
                         PRIMARY
                         KEY,
                         chat_data
                         TEXT
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS notebooks
                     (
                         id
                         TEXT
                         PRIMARY
                         KEY,
                         email
                         TEXT,
                         title
                         TEXT,
                         content
                         TEXT,
                         updated_at
                         TEXT
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS memories
                     (
                         id
                         INTEGER
                         PRIMARY
                         KEY
                         AUTOINCREMENT,
                         email
                         TEXT,
                         content
                         TEXT,
                         created_at
                         TEXT
                     )''')
        conn.commit();
        conn.close()

    def check_exists(self, email):
        conn = sqlite3.connect(self.path); res = conn.cursor().execute("SELECT * FROM users WHERE email=?",
                                                                       (email,)).fetchone(); conn.close(); return res is not None

    def register_final(self, email, password):
        conn = sqlite3.connect(self.path);
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users VALUES (?, ?, ?)",
                      (email, bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()), INITIAL_TOKENS)); c.execute(
                "INSERT INTO history VALUES (?, ?)", (email, "{}")); conn.commit(); return True, "OK"
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    def login(self, email, password):
        conn = sqlite3.connect(self.path);
        data = conn.cursor().execute("SELECT password_hash, tokens FROM users WHERE email=?", (email,)).fetchone();
        conn.close()
        if data and bcrypt.checkpw(password.encode('utf-8'), data[0]): return True, data[1]
        return False, 0

    def deduct_tokens(self, email, amount):
        conn = sqlite3.connect(self.path); c = conn.cursor(); c.execute(
            "UPDATE users SET tokens = MAX(0, tokens - ?) WHERE email=?", (amount, email)); conn.commit(); bal = \
        c.execute("SELECT tokens FROM users WHERE email=?", (email,)).fetchone()[0]; conn.close(); return bal

    def get_token_balance(self, email):
        conn = sqlite3.connect(self.path); res = conn.cursor().execute("SELECT tokens FROM users WHERE email=?",
                                                                       (email,)).fetchone(); conn.close(); return res[
            0] if res else 0

    def save_chats(self, email, chat_dict):
        conn = sqlite3.connect(self.path); conn.cursor().execute("UPDATE history SET chat_data = ? WHERE email=?",
                                                                 (json.dumps(chat_dict),
                                                                  email)); conn.commit(); conn.close()

    def load_chats(self, email):
        conn = sqlite3.connect(self.path); row = conn.cursor().execute("SELECT chat_data FROM history WHERE email=?",
                                                                       (email,)).fetchone(); conn.close(); return json.loads(
            row[0]) if row and row[0] else {}

    def save_notebook(self, nid, email, title, content):
        conn = sqlite3.connect(self.path); conn.cursor().execute(
            "INSERT OR REPLACE INTO notebooks (id, email, title, content, updated_at) VALUES (?, ?, ?, ?, ?)",
            (nid, email, title, content, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))); conn.commit(); conn.close()

    def load_notebooks_list(self, email):
        conn = sqlite3.connect(self.path); res = conn.cursor().execute(
            "SELECT id, title FROM notebooks WHERE email=? ORDER BY updated_at DESC",
            (email,)).fetchall(); conn.close(); return res

    def load_notebook_content(self, nid):
        conn = sqlite3.connect(self.path); res = conn.cursor().execute(
            "SELECT title, content FROM notebooks WHERE id=?",
            (nid,)).fetchone(); conn.close(); return res if res else ("Untitled", "")

    def add_memory(self, email, content):
        conn = sqlite3.connect(self.path); conn.cursor().execute(
            "INSERT INTO memories (email, content, created_at) VALUES (?, ?, ?)",
            (email, content, datetime.now().strftime("%Y-%m-%d"))); conn.commit(); conn.close()

    def get_memories(self, email):
        conn = sqlite3.connect(self.path); res = conn.cursor().execute(
            "SELECT id, content FROM memories WHERE email=? ORDER BY id DESC",
            (email,)).fetchall(); conn.close(); return res

    def delete_memory(self, mid):
        conn = sqlite3.connect(self.path); conn.cursor().execute("DELETE FROM memories WHERE id=?",
                                                                 (mid,)); conn.commit(); conn.close()


# --- CLIENT ---
def get_working_client():
    try:
        if requests.get(f"{LOCAL_URL}/models", timeout=1).status_code == 200: return OpenAI(base_url=LOCAL_URL,
                                                                                            api_key=API_KEY)
    except:
        pass
    return OpenAI(base_url=PUBLIC_URL, api_key=API_KEY)


client = get_working_client()
db = DatabaseManager()


# --- WIDGET ---
class FloatingWidget(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent);
        self.parent = parent;
        self.geometry("80x80+100+100");
        self.overrideredirect(True);
        self.attributes("-topmost", True);
        self.configure(fg_color="#000001");
        self.attributes("-transparentcolor", "#000001")
        try:
            self.logo_image = ctk.CTkImage(light_image=make_circle(Image.open(resource_path(LOGO_FILENAME))),
                                           size=(60, 60)); self.btn = ctk.CTkButton(self, text="",
                                                                                    image=self.logo_image, width=60,
                                                                                    height=60, corner_radius=30,
                                                                                    fg_color="#000001",
                                                                                    hover_color="#000001",
                                                                                    command=self.on_click)
        except:
            self.btn = ctk.CTkButton(self, text="H", font=FONT_HEADER, width=60, height=60, corner_radius=30,
                                     fg_color=HELIX_PURPLE, command=self.on_click)
        self.btn.place(relx=0.5, rely=0.5, anchor="center")
        self.bind("<ButtonPress-1>", self.start_move);
        self.bind("<B1-Motion>", self.do_move);
        self.hide_timer = None
        self.bind("<Enter>", self.on_enter);
        self.bind("<Leave>", self.on_leave);
        self.start_hide_timer()

    def start_move(self, e):
        self.x = e.x; self.y = e.y

    def do_move(self, e):
        self.geometry(f"+{self.winfo_x() + (e.x - self.x)}+{self.winfo_y() + (e.y - self.y)}")

    def on_click(self):
        self.parent.show_window("clipboard")

    def on_enter(self, e):
        self.attributes("-alpha", 1.0); self.after_cancel(self.hide_timer) if self.hide_timer else None

    def on_leave(self, e):
        self.start_hide_timer()

    def start_hide_timer(self):
        self.hide_timer = self.after(10000, lambda: self.attributes("-alpha", 0.01))


# --- SETTINGS ---
class SettingsModal(ctk.CTkToplevel):
    def __init__(self, parent, db, current_user, on_logout):
        super().__init__(parent);
        self.db = db;
        self.current_user = current_user;
        self.on_logout = on_logout;
        self.title("Settings");
        self.geometry("850x650");
        self.configure(fg_color=BG_DARK)
        self.nav_buttons = {};
        self.grid_columnconfigure(0, weight=0);
        self.grid_columnconfigure(1, weight=1);
        self.grid_rowconfigure(0, weight=1)
        nav_frame = ctk.CTkFrame(self, width=220, fg_color=BG_SIDEBAR, corner_radius=0);
        nav_frame.grid(row=0, column=0, sticky="nsew");
        nav_frame.grid_propagate(False)
        ctk.CTkLabel(nav_frame, text=f"👤 {self.current_user}", font=FONT_BOLD, text_color="white", anchor="w").pack(
            fill="x", padx=20, pady=(30, 5))
        ctk.CTkLabel(nav_frame, text="Free Plan", font=FONT_SMALL, text_color=HELIX_PURPLE, anchor="w").pack(fill="x",
                                                                                                             padx=20,
                                                                                                             pady=(0,
                                                                                                                   20))

        def nav_btn(text, page):
            btn = ctk.CTkButton(nav_frame, text=text, fg_color="transparent", hover_color=BG_CARD, anchor="w",
                                font=FONT_NORMAL, height=40, corner_radius=20,
                                command=lambda: self.switch_settings(page))
            btn.pack(fill="x", padx=10, pady=2);
            self.nav_buttons[page] = btn

        nav_btn("Personalization", "Personalization");
        nav_btn("General", "General")
        ctk.CTkFrame(nav_frame, height=1, fg_color=BG_CARD).pack(fill="x", pady=20, padx=20)
        ctk.CTkButton(nav_frame, text="Log out", fg_color="transparent", hover_color=BG_CARD, anchor="w",
                      text_color="#ff5555", font=FONT_NORMAL, height=40, corner_radius=20,
                      command=self.do_logout_modal).pack(fill="x", padx=10)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent");
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=40, pady=40);
        self.switch_settings("Personalization")

    def do_logout_modal(self):
        self.destroy(); self.on_logout()

    def switch_settings(self, page):
        for n, b in self.nav_buttons.items(): b.configure(fg_color=BG_CARD if n == page else "transparent")
        for w in self.content_frame.winfo_children(): w.destroy()
        ctk.CTkLabel(self.content_frame, text=page, font=FONT_HEADER, text_color="white").pack(anchor="w", pady=(0, 20))
        if page == "Personalization":
            ctk.CTkLabel(self.content_frame, text="Memory", font=FONT_SUBHEADER, text_color="white").pack(anchor="w",
                                                                                                          pady=(10, 5))
            add_f = ctk.CTkFrame(self.content_frame, fg_color="transparent");
            add_f.pack(fill="x", pady=10)
            self.mem_entry = ctk.CTkEntry(add_f, placeholder_text="Add memory...", height=45, corner_radius=22,
                                          border_width=0, fg_color=BG_INPUT, font=FONT_INPUT);
            self.mem_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
            ctk.CTkButton(add_f, text="Add", width=70, height=45, corner_radius=22, fg_color=HELIX_PURPLE,
                          text_color="black", command=self.add_mem).pack(side="right")
            self.mem_scroll = ctk.CTkScrollableFrame(self.content_frame, fg_color="transparent", height=400);
            self.mem_scroll.pack(fill="both", expand=True)
            self.refresh_memories()
        elif page == "General":
            ctk.CTkLabel(self.content_frame, text="App Version 3.5 (Gemini UI)", font=FONT_NORMAL,
                         text_color=TEXT_GRAY).pack(anchor="w")

    def refresh_memories(self):
        for w in self.mem_scroll.winfo_children(): w.destroy()
        for m in self.db.get_memories(self.current_user):
            row = ctk.CTkFrame(self.mem_scroll, fg_color=BG_CARD, corner_radius=15);
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=m[1], anchor="w", text_color="white", wraplength=500, font=FONT_NORMAL).pack(
                side="left", padx=15, pady=10)
            ctk.CTkButton(row, text="✕", width=30, height=30, fg_color="transparent", hover_color="#333",
                          corner_radius=15, command=lambda x=m[0]: self.del_mem(x)).pack(side="right", padx=10)

    def add_mem(self):
        self.db.add_memory(self.current_user,
                           self.mem_entry.get().strip()); self.refresh_memories(); self.mem_entry.delete(0, "end")

    def del_mem(self, mid):
        self.db.delete_memory(mid); self.refresh_memories()


# --- MAIN APP ---
class HelixApp(ctk.CTk):
    def __init__(self):
        super().__init__();
        self.title("HELIX");
        self.geometry("1366x900");
        self.configure(fg_color=BG_DARK)
        self.current_user = None;
        self.token_balance = 0;
        self.saved_chats = {};
        self.current_model_key = "Standard";
        self.current_note_id = None;
        self.attach_notebook_to_chat = False
        self.frames = {}
        self.container = ctk.CTkFrame(self, fg_color="transparent");
        self.container.pack(fill="both", expand=True)
        self.setup_login_screen();
        self.setup_otp_screen();
        self.setup_main_app()
        if load_session():
            self.current_user = load_session(); self.token_balance = db.get_token_balance(
                self.current_user); self.show_app()
        else:
            self.show_login()

    def setup_textbox_placeholder(self, textbox, placeholder_text, submit_func):
        textbox.insert("0.0", placeholder_text);
        textbox.configure(text_color=PLACEHOLDER_GRAY);
        textbox.has_placeholder = True

        def on_focus_in(e):
            if textbox.has_placeholder: textbox.delete("0.0", "end"); textbox.configure(
                text_color=TEXT_WHITE); textbox.has_placeholder = False

        def on_focus_out(e):
            if not textbox.get("0.0", "end").strip(): textbox.insert("0.0", placeholder_text); textbox.configure(
                text_color=PLACEHOLDER_GRAY); textbox.has_placeholder = True

        def on_enter(e):
            if not e.state & 0x0001:
                if not textbox.has_placeholder: submit_func()
                return "break"

        textbox.bind("<FocusIn>", on_focus_in);
        textbox.bind("<FocusOut>", on_focus_out);
        textbox.bind("<Return>", on_enter)

    # --- SCREENS ---
    def setup_login_screen(self):
        self.login_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)
        center = ctk.CTkFrame(self.login_frame, fg_color=BG_SIDEBAR, corner_radius=40, width=400, height=500);
        center.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(center, text="HELIX", font=FONT_HEADER, text_color=HELIX_PURPLE).place(relx=0.5, rely=0.15,
                                                                                            anchor="center")
        self.auth_tabs = ctk.CTkTabview(center, width=350, height=350, corner_radius=20, fg_color="transparent",
                                        segmented_button_selected_color=HELIX_PURPLE,
                                        segmented_button_unselected_color=BG_CARD);
        self.auth_tabs.place(relx=0.5, rely=0.55, anchor="center")

        login = self.auth_tabs.add("Login");
        signup = self.auth_tabs.add("Sign Up")
        self.entry_login_email = ctk.CTkEntry(login, placeholder_text="Email", height=55, corner_radius=27,
                                              fg_color=BG_INPUT, border_width=0);
        self.entry_login_email.pack(pady=10)
        self.entry_login_pass = ctk.CTkEntry(login, placeholder_text="Password", show="*", height=55, corner_radius=27,
                                             fg_color=BG_INPUT, border_width=0);
        self.entry_login_pass.pack(pady=10)
        ctk.CTkButton(login, text="Login", height=55, corner_radius=27, fg_color=HELIX_PURPLE, text_color="black",
                      font=FONT_BOLD, command=self.do_login).pack(pady=20)

        self.entry_reg_email = ctk.CTkEntry(signup, placeholder_text="New Email", height=55, corner_radius=27,
                                            fg_color=BG_INPUT, border_width=0);
        self.entry_reg_email.pack(pady=10)
        self.entry_reg_pass = ctk.CTkEntry(signup, placeholder_text="New Password", show="*", height=55,
                                           corner_radius=27, fg_color=BG_INPUT, border_width=0);
        self.entry_reg_pass.pack(pady=10)
        self.btn_reg = ctk.CTkButton(signup, text="Verify", height=55, corner_radius=27, fg_color=HELIX_PURPLE,
                                     text_color="black", font=FONT_BOLD, command=self.initiate_otp);
        self.btn_reg.pack(pady=20)

    def setup_otp_screen(self):
        self.otp_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)
        center = ctk.CTkFrame(self.otp_frame, fg_color=BG_SIDEBAR, corner_radius=40);
        center.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(center, text="VERIFY", font=FONT_HEADER, text_color=HELIX_PURPLE).pack(pady=30, padx=80)
        self.entry_otp = ctk.CTkEntry(center, placeholder_text="Code", height=60, width=200, corner_radius=30,
                                      font=("Segoe UI", 24), justify="center", fg_color=BG_INPUT, border_width=0);
        self.entry_otp.pack(pady=20)
        ctk.CTkButton(center, text="Submit", height=50, width=200, corner_radius=25, fg_color=HELIX_PURPLE,
                      text_color="black", command=self.verify_otp).pack(pady=20)
        ctk.CTkButton(center, text="Back", height=40, width=200, fg_color="transparent", command=self.show_login).pack(
            pady=10)

    def setup_main_app(self):
        self.app_frame = ctk.CTkFrame(self.container, fg_color=BG_DARK)

        # --- SIDEBAR (Initial Setup) ---
        self.sidebar = ctk.CTkFrame(self.app_frame, width=280, fg_color=BG_SIDEBAR, corner_radius=0)
        # We DO NOT pack it here. The switch_tab logic handles packing it.
        # But we initialize its children:

        # Logo Area
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=80);
        logo_frame.pack(fill="x", padx=25, pady=25)
        try:
            icon = ctk.CTkImage(light_image=Image.open(resource_path(LOGO_FILENAME)), size=(35, 35)); ctk.CTkLabel(
                logo_frame, text="", image=icon).pack(side="left")
        except:
            pass
        ctk.CTkLabel(logo_frame, text="HELIX", font=FONT_HEADER, text_color=TEXT_WHITE).pack(side="left", padx=15)

        # New Chat Button (Pill Shape)
        ctk.CTkButton(self.sidebar, text="+ New Chat", fg_color=BG_CARD, hover_color=BG_INPUT, height=50,
                      corner_radius=25, font=FONT_BOLD, text_color=TEXT_GRAY, command=self.create_new_chat).pack(
            fill="x", padx=20, pady=10)

        # History List
        ctk.CTkLabel(self.sidebar, text="Recent", font=FONT_SMALL, text_color=TEXT_GRAY).pack(anchor="w", padx=25,
                                                                                              pady=(20, 5))
        self.chat_list_frame = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent");
        self.chat_list_frame.pack(fill="both", expand=True, padx=10)

        # Settings
        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=60);
        footer.pack(fill="x", side="bottom", padx=20, pady=20)
        ctk.CTkButton(footer, text="⚙️ Settings", fg_color="transparent", hover_color=BG_CARD, anchor="w", height=45,
                      corner_radius=22, font=FONT_NORMAL, command=self.open_settings).pack(fill="x")

        # --- MAIN CONTENT AREA ---
        self.main_area = ctk.CTkFrame(self.app_frame, fg_color=BG_DARK);
        self.main_area.pack(side="right", fill="both", expand=True)

        # Custom Tab Switcher (Floating Pill Style at Bottom)
        tab_switcher = ctk.CTkFrame(self.main_area, fg_color=BG_CARD, corner_radius=20, height=40)
        tab_switcher.place(relx=0.5, rely=0.96, anchor="center")

        # We use a custom function to switch so we can toggle sidebar
        def tab_btn(txt):
            ctk.CTkButton(tab_switcher, text=txt, fg_color="transparent", hover_color=BG_INPUT, width=80, height=30,
                          corner_radius=15, font=FONT_SMALL, command=lambda: self.switch_tab(txt)).pack(side="left",
                                                                                                        padx=5, pady=5)

        tab_btn("Talk to AI");
        tab_btn("Notebook");
        tab_btn("Quick Fix")

        self.setup_talk_to_ai();
        self.setup_notebook();
        self.setup_quick_fix()
        self.widget = FloatingWidget(self)

    # --- TAB & SIDEBAR LOGIC ---
    def switch_tab(self, tab_name):
        for name, frame in self.frames.items():
            if name == tab_name:
                frame.pack(fill="both", expand=True)
            else:
                frame.pack_forget()

        if tab_name == "Talk to AI":
            # Show sidebar, pack it LEFT of main_area
            self.sidebar.pack(side="left", fill="y", before=self.main_area)
        else:
            # Hide sidebar
            self.sidebar.pack_forget()

    # --- CHAT TAB (GEMINI STYLE INPUT ISLAND) ---
    def setup_talk_to_ai(self):
        self.frames["Talk to AI"] = ctk.CTkFrame(self.main_area, fg_color="transparent")
        tab = self.frames["Talk to AI"]
        tab.grid_columnconfigure(0, weight=1);
        tab.grid_rowconfigure(0, weight=1);
        tab.grid_rowconfigure(1, weight=0)

        # Welcome Screen
        self.welcome_frame = ctk.CTkFrame(tab, fg_color="transparent");
        self.welcome_frame.grid(row=0, column=0, sticky="nsew")
        center = ctk.CTkFrame(self.welcome_frame, fg_color="transparent");
        center.place(relx=0.5, rely=0.40, anchor="center")
        try:
            icon = ctk.CTkImage(light_image=Image.open(resource_path(LOGO_FILENAME)), size=(70, 70)); ctk.CTkLabel(
                center, text="", image=icon).pack(pady=10)
        except:
            pass
        ctk.CTkLabel(center, text="Hello, I'm Helix", font=("Google Sans", 36), text_color="white").pack(pady=5)
        ctk.CTkLabel(center, text="How can I help you today?", font=("Google Sans", 20), text_color=TEXT_GRAY).pack(
            pady=0)

        # Chat Box (Hidden initially)
        self.chat_box = ctk.CTkTextbox(tab, font=FONT_NORMAL, wrap="word", fg_color="transparent",
                                       text_color=TEXT_WHITE, activate_scrollbars=True)
        # It's in grid row 0, same as welcome

        # --- THE INPUT ISLAND ---
        input_wrapper = ctk.CTkFrame(tab, fg_color="transparent")
        input_wrapper.grid(row=1, column=0, sticky="ew", padx=120, pady=(0, 100))

        self.input_pill = ctk.CTkFrame(input_wrapper, fg_color=BG_INPUT, height=120, corner_radius=32)
        self.input_pill.pack(fill="x", expand=True)

        self.chat_entry = ctk.CTkTextbox(self.input_pill, font=FONT_INPUT, height=50, fg_color="transparent",
                                         text_color=TEXT_WHITE, wrap="word", activate_scrollbars=False)
        self.chat_entry.pack(fill="x", padx=20, pady=(15, 5))
        self.setup_textbox_placeholder(self.chat_entry, "Ask Helix anything...", self.send_chat)

        tools_row = ctk.CTkFrame(self.input_pill, fg_color="transparent", height=40)
        tools_row.pack(fill="x", padx=10, pady=(0, 10))

        self.btn_attach = ctk.CTkButton(tools_row, text="+", width=35, height=35, fg_color=BG_CARD, hover_color=BG_DARK,
                                        text_color=TEXT_GRAY, font=("Arial", 20), corner_radius=17,
                                        command=self.toggle_attach)
        self.btn_attach.pack(side="left", padx=(10, 5))

        self.model_var = ctk.StringVar(value="Standard")
        self.model_dropdown = ctk.CTkOptionMenu(tools_row, variable=self.model_var, values=["Standard", "Thinking"],
                                                command=self.change_model, width=110, height=32, corner_radius=16,
                                                fg_color=BG_CARD, button_color=BG_CARD, button_hover_color=BG_DARK,
                                                text_color=TEXT_GRAY)
        self.model_dropdown.pack(side="left", padx=5)

        self.btn_send = ctk.CTkButton(tools_row, text="➤", width=50, height=35, fg_color=HELIX_PURPLE,
                                      text_color="black", hover_color=HELIX_HOVER, corner_radius=17, font=("Arial", 16),
                                      command=self.send_chat)
        self.btn_send.pack(side="right", padx=10)

    # --- NOTEBOOK TAB ---
    def setup_notebook(self):
        self.frames["Notebook"] = ctk.CTkFrame(self.main_area, fg_color="transparent")
        tab = self.frames["Notebook"]
        tab.grid_columnconfigure(0, weight=0);
        tab.grid_columnconfigure(1, weight=1);
        tab.grid_rowconfigure(0, weight=1)
        # File list
        list_frame = ctk.CTkFrame(tab, width=220, fg_color=BG_SIDEBAR, corner_radius=20);
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15));
        list_frame.grid_propagate(False)
        ctk.CTkButton(list_frame, text="+ New Page", fg_color=BG_CARD, hover_color=BG_INPUT, height=45,
                      corner_radius=22, command=self.notebook_new).pack(fill="x", padx=15, pady=15)
        self.notebook_list_frame = ctk.CTkScrollableFrame(list_frame, fg_color="transparent");
        self.notebook_list_frame.pack(fill="both", expand=True)
        # Editor
        editor = ctk.CTkFrame(tab, fg_color=BG_INPUT, corner_radius=20);
        editor.grid(row=0, column=1, sticky="nsew")
        editor.grid_rowconfigure(1, weight=1);
        editor.grid_columnconfigure(0, weight=1)
        self.note_title = ctk.CTkEntry(editor, font=FONT_HEADER, fg_color="transparent", border_width=0,
                                       placeholder_text="Untitled");
        self.note_title.grid(row=0, column=0, sticky="ew", padx=30, pady=(20, 10))
        ctk.CTkButton(editor, text="Save", width=70, height=35, corner_radius=17, fg_color=BG_CARD, hover_color=BG_DARK,
                      command=self.notebook_save).grid(row=0, column=1, padx=30)
        self.notebook = ctk.CTkTextbox(editor, font=FONT_NORMAL, fg_color="transparent", wrap="word");
        self.notebook.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=30)
        # AI Bar
        ai_bar = ctk.CTkFrame(editor, fg_color=BG_CARD, height=60, corner_radius=30);
        ai_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=30, pady=(20, 80))
        self.note_prompt = ctk.CTkTextbox(ai_bar, height=35, fg_color="transparent", font=FONT_INPUT, wrap="word");
        self.note_prompt.pack(side="left", fill="x", expand=True, padx=20, pady=12)
        self.setup_textbox_placeholder(self.note_prompt, "Instruct Helix to edit...", self.notebook_ai_run)
        ctk.CTkButton(ai_bar, text="Generate", width=90, height=40, corner_radius=20, fg_color=HELIX_PURPLE,
                      text_color="black", command=self.notebook_ai_run).pack(side="right", padx=10)

    # --- QUICK FIX TAB ---
    def setup_quick_fix(self):
        self.frames["Quick Fix"] = ctk.CTkFrame(self.main_area, fg_color="transparent")
        tab = self.frames["Quick Fix"]
        tab.grid_columnconfigure(0, weight=1);
        tab.grid_rowconfigure(0, weight=1)
        self.q_result = ctk.CTkTextbox(tab, font=FONT_NORMAL, fg_color=BG_INPUT, corner_radius=20);
        self.q_result.grid(row=0, column=0, sticky="nsew", padx=60, pady=60)

        bar = ctk.CTkFrame(tab, fg_color=BG_INPUT, height=70, corner_radius=35);
        bar.grid(row=1, column=0, sticky="ew", padx=60, pady=(0, 90))
        self.q_prompt = ctk.CTkTextbox(bar, height=45, fg_color="transparent", font=FONT_INPUT);
        self.q_prompt.pack(side="left", fill="x", expand=True, padx=25, pady=12)
        self.setup_textbox_placeholder(self.q_prompt, "Custom instruction...", self.quick_fix_custom_run)
        ctk.CTkButton(bar, text="Refine", width=100, height=45, corner_radius=22, fg_color=HELIX_PURPLE,
                      text_color="black", command=self.quick_fix_custom_run).pack(side="right", padx=12)

    # --- LOGIC ---
    def open_settings(self):
        SettingsModal(self, db, self.current_user, self.do_logout)

    def toggle_attach(self):
        self.attach_notebook_to_chat = not self.attach_notebook_to_chat; self.btn_attach.configure(
            fg_color=HELIX_PURPLE if self.attach_notebook_to_chat else BG_CARD)

    def notebook_new(self):
        self.current_note_id = str(uuid.uuid4()); self.note_title.delete(0, "end"); self.note_title.insert(0,
                                                                                                           "Untitled"); self.notebook.delete(
            "0.0", "end"); self.refresh_notebook_list()

    def notebook_save(self):
        if not self.current_note_id: self.current_note_id = str(uuid.uuid4())
        db.save_notebook(self.current_note_id, self.current_user, self.note_title.get(),
                         self.notebook.get("0.0", "end").strip());
        self.refresh_notebook_list()

    def refresh_notebook_list(self):
        for w in self.notebook_list_frame.winfo_children(): w.destroy()
        for n in db.load_notebooks_list(self.current_user): ctk.CTkButton(self.notebook_list_frame, text=n[1],
                                                                          fg_color="transparent", hover_color=BG_CARD,
                                                                          anchor="w", height=40, corner_radius=20,
                                                                          command=lambda x=n[0]: self.load_notebook(
                                                                              x)).pack(fill="x", pady=2)

    def load_notebook(self, nid):
        self.current_note_id = nid; t, c = db.load_notebook_content(nid); self.note_title.delete(0,
                                                                                                 "end"); self.note_title.insert(
            0, t); self.notebook.delete("0.0", "end"); self.notebook.insert("0.0", c)

    def notebook_ai_run(self):
        p = self.note_prompt.get("0.0", "end").strip();
        if not p or self.note_prompt.has_placeholder: return
        self.note_prompt.delete("0.0", "end");
        self.setup_textbox_placeholder(self.note_prompt, "Working...", self.notebook_ai_run)
        threading.Thread(target=self.run_ai_stream, args=([{"role": "system", "content": f"Editor. Inst: {p}"},
                                                           {"role": "user",
                                                            "content": self.notebook.get("0.0", "end")}],
                                                          self.notebook), daemon=True).start()

    def quick_fix_custom_run(self):
        p = self.q_prompt.get("0.0", "end").strip();
        t = self.q_result.get("0.0", "end").strip()
        if not p or self.q_prompt.has_placeholder: return
        self.q_result.delete("0.0", "end");
        self.q_prompt.delete("0.0", "end");
        self.setup_textbox_placeholder(self.q_prompt, "Refining...", self.quick_fix_custom_run)
        threading.Thread(target=self.run_ai_stream,
                         args=([{"role": "system", "content": f"Editor. Inst: {p}"}, {"role": "user", "content": t}],
                               self.q_result), daemon=True).start()

    def start_quick_fix(self, text):
        self.q_result.delete("0.0", "end");
        self.q_result.insert("end", "Fixing...");
        self.switch_tab("Quick Fix")
        threading.Thread(target=self.run_ai_stream,
                         args=([{"role": "system", "content": PROMPTS["Fix"]}, {"role": "user", "content": text}],
                               self.q_result), daemon=True).start()

    def change_model(self, v):
        self.current_model_key = v

    def show_login(self):
        self.app_frame.pack_forget(); self.otp_frame.pack_forget(); self.login_frame.pack(fill="both", expand=True)

    def show_otp(self):
        self.login_frame.pack_forget(); self.otp_frame.pack(fill="both", expand=True)

    def show_app(self):
        self.login_frame.pack_forget(); self.otp_frame.pack_forget(); self.app_frame.pack(fill="both",
                                                                                          expand=True); self.saved_chats = db.load_chats(
            self.current_user); self.refresh_sidebar(); self.create_new_chat(); self.switch_tab("Talk to AI")

    def do_login(self):
        email = self.entry_login_email.get();
        p = self.entry_login_pass.get()
        success, tokens = db.login(email, p);
        self.current_user = email;
        self.token_balance = tokens;
        save_session(email);
        self.show_app() if success else messagebox.showerror("Error", "Failed")

    def do_logout(self):
        clear_session(); self.current_user = None; self.show_login()

    def initiate_otp(self):
        self.pending_email = self.entry_reg_email.get(); self.pending_pass = self.entry_reg_pass.get(); self.pending_otp = str(
            random.randint(100000, 999999)); threading.Thread(
            target=lambda: send_otp_email(self.pending_email, self.pending_otp)).start(); self.show_otp()

    def verify_otp(self):
        if self.entry_otp.get().strip() == self.pending_otp: db.register_final(self.pending_email,
                                                                               self.pending_pass); self.current_user = self.pending_email; self.token_balance = INITIAL_TOKENS; save_session(
            self.current_user); self.show_app()

    def get_system_prompt(self, key):
        base = PROMPTS[key];
        mems = db.get_memories(self.current_user)
        if mems: base += "\nMemories:\n" + "\n".join([m[1] for m in mems])
        if self.attach_notebook_to_chat and self.current_note_id: base += f"\nNotebook: {db.load_notebook_content(self.current_note_id)[1]}"
        return base

    def send_chat(self, text=None):
        if not self.check_tokens(): return
        msg = text if text else self.chat_entry.get("0.0", "end").strip()
        if not msg or self.chat_entry.has_placeholder: return
        self.chat_entry.delete("0.0", "end");
        self.setup_textbox_placeholder(self.chat_entry, "Ask Helix anything...", self.send_chat)
        self.welcome_frame.grid_forget();
        self.chat_box.grid(row=0, column=0, sticky="nsew", padx=120, pady=(40, 100))  # Align with input
        self.chat_box.insert("end", f"\n\n\n👤 YOU: {msg}\n");
        self.chat_box.see("end")
        self.saved_chats[self.current_chat_id]["msgs"].append({"role": "user", "content": msg})
        if len(self.saved_chats[self.current_chat_id]["msgs"]) == 1: self.saved_chats[self.current_chat_id][
            "title"] = msg; self.refresh_sidebar()
        self.save_history();
        threading.Thread(target=self.run_ai_stream, args=(
            [{"role": "system", "content": self.get_system_prompt("Chat")}, {"role": "user", "content": msg}],
            self.chat_box, True), daemon=True).start()

    def create_new_chat(self):
        new_id = str(uuid.uuid4());
        self.saved_chats[new_id] = {"title": "New Chat", "msgs": []};
        self.current_chat_id = new_id;
        self.chat_box.delete("0.0", "end")
        self.chat_box.grid_forget();
        self.welcome_frame.grid(row=0, column=0, sticky="nsew");
        self.refresh_sidebar()

    def refresh_sidebar(self):
        for w in self.chat_list_frame.winfo_children(): w.destroy()
        for c_id in reversed(list(self.saved_chats.keys())): ctk.CTkButton(self.chat_list_frame,
                                                                           text=self.saved_chats[c_id]["title"][
                                                                                    :20] + "...", anchor="w",
                                                                           fg_color="transparent", hover_color=BG_CARD,
                                                                           height=40, corner_radius=20,
                                                                           font=FONT_NORMAL,
                                                                           command=lambda x=c_id: self.load_chat(
                                                                               x)).pack(fill="x", pady=2)

    def load_chat(self, chat_id):
        self.current_chat_id = chat_id;
        data = self.saved_chats[chat_id];
        self.chat_box.delete("0.0", "end")
        self.welcome_frame.grid_forget();
        self.chat_box.grid(row=0, column=0, sticky="nsew", padx=120, pady=(40, 100))
        for m in data["msgs"]: role = "👤 YOU" if m["role"] == "user" else "🧬 HELIX"; self.chat_box.insert("end",
                                                                                                          f"\n\n\n{role}: {m['content']}\n"); self.chat_box.see(
            "end")

    def run_ai_stream(self, msgs, widget, is_chat=False):
        try:
            full_response = ""
            if is_chat:
                self.after(0, lambda: widget.insert("end", "\n\n🧬 HELIX: "))
            elif not is_chat:
                self.after(0, lambda: widget.delete("0.0", "end"))
            stream = client.chat.completions.create(model=MODEL_CONFIG[self.current_model_key]["id"], messages=msgs,
                                                    temperature=0.7, stream=True)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    c = chunk.choices[0].delta.content;
                    full_response += c
                    self.after(0, lambda x=c: widget.insert("end", x));
                    self.after(0, lambda: widget.see("end"))
            if is_chat: self.saved_chats[self.current_chat_id]["msgs"].append(
                {"role": "assistant", "content": full_response}); self.after(0, self.save_history)
            self.after(0, lambda: self.charge_tokens_for_words(full_response))
        except Exception as e:
            self.after(0, lambda: widget.insert("end", f"\n[Error: {e}]"))

    def check_tokens(self):
        return True

    def charge_tokens_for_words(self, text):
        c = len(text.split()) * MODEL_CONFIG[self.current_model_key]["cost_multiplier"]
        self.token_balance = db.deduct_tokens(self.current_user, c)

    def show_window(self, mode):
        self.deiconify();
        self.attributes("-topmost", True)
        if not self.current_user: self.show_login(); return
        if mode == "clipboard": self.start_quick_fix(pyperclip.paste())

    def save_history(self):
        db.save_chats(self.current_user, self.saved_chats)

if __name__ == "__main__":
    app = HelixApp()
    app.mainloop()
