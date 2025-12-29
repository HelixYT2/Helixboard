const { ipcRenderer } = require('electron');

const API_URL = "http://127.0.0.1:5000";

// State
let currentUser = null;
let currentChatId = null;
let currentNoteId = null;
let currentContactId = null;

// DOM Elements
const pages = {
    talk: document.getElementById('page-talk'),
    canvas: document.getElementById('page-canvas'),
    messages: document.getElementById('page-messages'),
    quickfix: document.getElementById('page-quickfix')
};

const navBtns = document.querySelectorAll('.nav-btn');

// --- AUTH ---
async function login(email, password) {
    try {
        const res = await fetch(`${API_URL}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            currentUser = email;
            document.getElementById('login-overlay').classList.add('hidden');
            document.getElementById('app-container').classList.remove('hidden');
            initApp();
        } else {
            alert(data.message);
        }
    } catch (e) {
        console.error(e);
        alert("Connection failed");
    }
}

document.getElementById('auth-btn').addEventListener('click', () => {
    const e = document.getElementById('email').value;
    const p = document.getElementById('password').value;
    login(e, p);
});

// --- NAVIGATION ---
navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        // Switch Page
        const target = btn.dataset.tab;
        Object.values(pages).forEach(p => p.classList.remove('active'));
        pages[target.replace('page-', '')].classList.add('active'); // simplified map

        // Update Nav
        navBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        // Sidebar logic
        const sb = document.getElementById('sidebar');
        if (target === 'page-talk') sb.style.display = 'flex';
        else sb.style.display = 'none';
    });
});

// --- APP INIT ---
async function initApp() {
    loadChatList();
    loadNotebookList();
}

async function loadChatList() {
    const res = await fetch(`${API_URL}/chat/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: currentUser })
    });
    const chats = await res.json();
    const list = document.getElementById('chat-list');
    list.innerHTML = '';
    // Reverse order
    Object.keys(chats).reverse().forEach(cid => {
        const c = chats[cid];
        const div = document.createElement('div');
        div.className = 'sidebar-item';
        div.innerText = "💬 " + (c.title || "New Chat");
        div.onclick = () => loadChat(cid, c);
        list.appendChild(div);
    });
}

function loadChat(cid, data) {
    currentChatId = cid;
    document.getElementById('welcome-screen').classList.add('hidden');
    document.getElementById('chat-container').classList.remove('hidden');
    const box = document.getElementById('chat-messages');
    box.innerHTML = '';
    (data.msgs || []).forEach(m => addBubble(m.role, m.content));
}

function addBubble(role, text) {
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `bubble ${role}`;
    div.innerText = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// --- CHAT SEND ---
document.getElementById('send-btn').addEventListener('click', sendChat);
async function sendChat() {
    const inp = document.getElementById('chat-input');
    const txt = inp.value.trim();
    if (!txt) return;

    addBubble('user', txt);
    inp.value = '';

    // Stream response
    // Construct msg history (simplified)
    const msgs = [{ role: "user", content: txt }]; // Should load full context

    // In a real app, we'd fetch currentChatId's history first
    // For this demo, we stream just the response

    const assistantBubble = document.createElement('div');
    assistantBubble.className = 'bubble assistant';
    assistantBubble.innerText = "...";
    document.getElementById('chat-messages').appendChild(assistantBubble);

    try {
        const response = await fetch(`${API_URL}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: msgs, model: "Standard" })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const json = JSON.parse(line.substring(6));
                        if (json.content) {
                            if (fullText === "") assistantBubble.innerText = "";
                            fullText += json.content;
                            assistantBubble.innerText = fullText;
                        }
                    } catch (e) {}
                }
            }
        }
    } catch (e) {
        assistantBubble.innerText = "[Error]";
    }
}

// --- CANVAS ---
async function loadNotebookList() {
    const res = await fetch(`${API_URL}/notebooks/list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: currentUser })
    });
    const notes = await res.json();
    const grid = document.getElementById('canvas-grid');
    grid.innerHTML = '';
    notes.forEach(n => {
        const div = document.createElement('div');
        div.className = 'notebook-card';
        div.innerText = n.title || "Untitled";
        div.onclick = () => openNotebook(n.id);
        grid.appendChild(div);
    });

    // Also update sidebar
    const list = document.getElementById('notebook-list');
    list.innerHTML = '';
    notes.forEach(n => {
        const div = document.createElement('div');
        div.className = 'sidebar-item';
        div.innerText = "📝 " + (n.title || "Untitled");
        div.onclick = () => openNotebook(n.id);
        list.appendChild(div);
    });
}

async function openNotebook(nid) {
    currentNoteId = nid;
    const res = await fetch(`${API_URL}/notebooks/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: nid })
    });
    const data = await res.json();
    document.getElementById('note-title').value = data.title;
    document.getElementById('note-content').value = data.content;

    document.getElementById('canvas-dashboard').classList.add('hidden');
    document.getElementById('canvas-editor').classList.remove('hidden');
}

document.getElementById('canvas-back').addEventListener('click', () => {
    saveNotebook(); // auto save
    document.getElementById('canvas-editor').classList.add('hidden');
    document.getElementById('canvas-dashboard').classList.remove('hidden');
    loadNotebookList();
});

async function saveNotebook() {
    if (!currentNoteId) return; // Should create new ID if null
    const title = document.getElementById('note-title').value;
    const content = document.getElementById('note-content').value;
    await fetch(`${API_URL}/notebooks/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentNoteId, email: currentUser, title, content })
    });
}

// --- DRAFT MODE ---
const draftOverlay = document.getElementById('draft-overlay');
const draftInput = document.getElementById('draft-input');
const draftPreview = document.getElementById('draft-preview');
const draftHistory = document.getElementById('draft-history');

document.getElementById('canvas-draft-mode').addEventListener('click', () => {
    draftOverlay.classList.remove('hidden');
    draftPreview.value = document.getElementById('note-content').value;
    draftHistory.innerHTML = '';
    draftInput.value = '';
});

document.getElementById('draft-cancel').addEventListener('click', () => {
    draftOverlay.classList.add('hidden');
});

document.getElementById('draft-insert').addEventListener('click', () => {
    document.getElementById('note-content').value = draftPreview.value;
    saveNotebook();
    draftOverlay.classList.add('hidden');
});

document.getElementById('draft-run-btn').addEventListener('click', async () => {
    const inst = draftInput.value.trim();
    if (!inst) return;

    // Add instruction to history
    const bubble = document.createElement('div');
    bubble.className = 'draft-bubble';
    bubble.innerText = inst;
    draftHistory.appendChild(bubble);

    // Hide input (mimic Python fix)
    document.querySelector('.draft-input-pill').style.display = 'none';
    draftInput.value = '';

    try {
        // Mock stream for demo (server requires valid LLM endpoint)
        // In real app, call /chat/stream with system prompt "You are an AI writing assistant..."
        // Here we simulate it
        const current = draftPreview.value;
        const msgs = [
            { role: "system", content: "Output ONLY the updated text." },
            { role: "user", content: `Current:\n${current}\n\nInstruction: ${inst}` }
        ];

        const response = await fetch(`${API_URL}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ messages: msgs, model: "Standard" })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        draftPreview.value = ""; // Clear for stream

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const json = JSON.parse(line.substring(6));
                        if (json.content) draftPreview.value += json.content;
                    } catch (e) {}
                }
            }
        }
    } catch (e) {
        console.error(e);
    } finally {
        document.querySelector('.draft-input-pill').style.display = 'flex';
    }
});
