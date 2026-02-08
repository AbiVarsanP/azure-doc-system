import sqlite3
import os

DB_PATH = "auth.db"

if os.path.exists(DB_PATH):
    print(f"{DB_PATH} already exists; skipping creation.")
else:
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE staff (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        password TEXT,
        mentor_email TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_email TEXT,
        filename TEXT,
        cert_type TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute(
        "INSERT INTO staff (email, password) VALUES (?, ?)",
        ("mentor@college.com", "1234"),
    )

    db.commit()
    db.close()
    print(f"Created {DB_PATH}")
