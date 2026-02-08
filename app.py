from azure.storage.blob import BlobServiceClient
import os
from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "secret123"  # change later


blob_service = BlobServiceClient(
    account_url=f"https://{os.getenv('AZURE_STORAGE_ACCOUNT')}.blob.core.windows.net",
    credential=os.getenv("AZURE_STORAGE_KEY")
)
container = os.getenv("AZURE_CONTAINER")


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
    
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if session.get("role") != "student":
        return redirect("/login")

    if request.method == "POST":
        file = request.files["file"]
        cert_type = request.form["cert_type"]

        blob_client = blob_service.get_blob_client(
            container=container,
            blob=file.filename
        )
        blob_client.upload_blob(file, overwrite=True)

        db = get_db()
        db.execute(
            "INSERT INTO documents (student_email, filename, cert_type) VALUES (?, ?, ?)",
            (session["email"], file.filename, cert_type)
        )
        db.commit()

        return "Uploaded successfully"

    return render_template("upload.html")

@app.route("/documents")
def documents():
    if session.get("role") != "staff":
        return redirect("/login")

    db = get_db()
    docs = db.execute("SELECT * FROM documents").fetchall()

    return render_template("documents.html", docs=docs)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run()
