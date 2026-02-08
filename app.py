from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"  # change later

def get_db():
    return sqlite3.connect("auth.db")

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form["role"]
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()

        if role == "staff":
            cur.execute("SELECT * FROM staff WHERE email=? AND password=?", (email, password))
        else:
            cur.execute("SELECT * FROM students WHERE email=? AND password=?", (email, password))

        user = cur.fetchone()

        if user:
            session["role"] = role
            session["email"] = email
            return redirect("/dashboard")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "role" not in session:
        return redirect("/login")

    if session["role"] == "staff":
        return render_template("staff_dashboard.html")
    else:
        return render_template("student_dashboard.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run()
