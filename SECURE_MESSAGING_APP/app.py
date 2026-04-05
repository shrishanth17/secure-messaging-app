# app.py
from flask import Flask, render_template, request, session, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
from cryptography.fernet import Fernet, InvalidToken
import os
import time
import secrets

app = Flask(__name__)
app.config["SECRET_KEY"] = "secure_messaging_secret_key"

# In-memory "database"
USERS = {}          # { username: { "password": "pass", "socket_id": None, "status": "online" } }
MESSAGES = []       # [ { "sender": u1, "receiver": u2, "encrypted": base64, "timestamp": t, "self_destroy": sec } ]
KEYS = {}           # { username: Fernet key }

socketio = SocketIO(app, cors_allowed_origins="*")

# Utility: generate or get user key
def get_user_key(username):
    if username not in KEYS:
        KEYS[username] = Fernet.generate_key()
    return KEYS[username]

def encrypt_msg(username, plaintext):
    key = get_user_key(username)
    f = Fernet(key)
    return f.encrypt(plaintext.encode("utf-8"))

def decrypt_msg(username, ciphertext_b64):
    try:
        key = get_user_key(username)
        f = Fernet(key)
        decrypted = f.decrypt(ciphertext_b64)
        return decrypted.decode("utf-8")
    except InvalidToken:
        return "[Decryption failed - corrupted or invalid ciphertext]"

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    username = request.form.get("username")
    password = request.form.get("password")

    if not username or not username.strip():
        return "Username required", 400

    # Simple in-memory storage (no DB)
    if username not in USERS:
        USERS[username] = {
            "password": password or "123",
            "socket_id": None,
            "status": "offline",
        }
    else:
        if USERS[username]["password"] != password:
            return "Invalid password", 400

    session["username"] = username
    USERS[username]["status"] = "online"
    return redirect("/chat")

@app.route("/chat")
def chat():
    username = session.get("username")
    if not username:
        return redirect("/")
    online_users = [
        u for u in USERS if u != username and USERS[u]["status"] == "online"
    ]
    return render_template("chat.html", username=username, users=online_users)

# --- SocketIO Events ---

@socketio.on("connect")
def handle_connect(auth):
    username = session.get("username")
    if not username:
        return

    if username not in USERS:
        USERS[username] = {
            "password": "unknown",
            "socket_id": None,
            "status": "offline",
        }

    USERS[username]["socket_id"] = request.sid
    USERS[username]["status"] = "online"
    
    # BROADCAST updated user list to ALL clients
    emit("update_users_list", {
        "users": [u for u in USERS if USERS[u]["status"] == "online"]
    }, broadcast=True)

@socketio.on("disconnect")
def handle_disconnect():
    username = session.get("username")
    if not username:
        return

    if username in USERS:
        USERS[username]["socket_id"] = None
        USERS[username]["status"] = "offline"
        emit("update_users_list", {
            "users": [u for u in USERS if USERS[u]["status"] == "online"]
        }, broadcast=True)

@socketio.on("send_message")
def handle_message(data):
    sender = session.get("username")
    receiver = data.get("receiver")
    plaintext = data.get("text")
    timestamp = time.time()
    self_destruct = data.get("self_destruct", 0)

    if not plaintext or not receiver:
        return

    # Encrypt for sender (store encrypted)
    encrypted = encrypt_msg(sender, plaintext)

    # Save message
    MESSAGES.append({
        "sender": sender,
        "receiver": receiver,
        "encrypted": encrypted,
        "timestamp": timestamp,
        "self_destruct": self_destruct,
    })

    # Send to receiver (only if online)
    receiver_info = USERS.get(receiver)
    if receiver_info and receiver_info["socket_id"]:
        decrypt_text = decrypt_msg(sender, encrypted)
        emit(
            "receive_message",
            {
                "sender": sender,
                "text": decrypt_text,
                "timestamp": timestamp,
                "encrypted_status": "Encrypted message sent ✅",
            },
            room=receiver_info["socket_id"],
        )

@socketio.on("join_user")
def handle_join_user(data):
    receiver = data["receiver"]
    username = session.get("username")
    if not username:
        return

    # Send all prior messages between sender ↔ receiver
    history = []
    for msg in MESSAGES:
        if (
            (msg["sender"] == username and msg["receiver"] == receiver)
            or (msg["sender"] == receiver and msg["receiver"] == username)
        ):
            if msg["sender"] == username:
                plain = decrypt_msg(username, msg["encrypted"])
            else:
                plain = decrypt_msg(msg["sender"], msg["encrypted"])
            history.append({
                "sender": msg["sender"],
                "text": plain,
                "timestamp": msg["timestamp"],
            })
    emit("message_history", {"history": history})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
