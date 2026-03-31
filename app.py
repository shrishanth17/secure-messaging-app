from flask import Flask, render_template, request, redirect, session
from cryptography.fernet import Fernet

app = Flask(__name__)
app.secret_key = "secret123"

# 🔐 Generate key (in real project store securely)
key = Fernet.generate_key()
cipher = Fernet(key)

messages = []

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        session["user"] = username
        return redirect("/chat")
    return render_template("login.html")

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        msg = request.form["message"]

        # 🔐 Encrypt message
        encrypted = cipher.encrypt(msg.encode())

        messages.append({
            "user": session["user"],
            "text": encrypted
        })

    # 🔓 Decrypt messages for display
    decrypted_messages = []
    for m in messages:
        decrypted = cipher.decrypt(m["text"]).decode()
        decrypted_messages.append({
            "user": m["user"],
            "text": decrypted
        })

    return render_template("chat.html", messages=decrypted_messages)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)