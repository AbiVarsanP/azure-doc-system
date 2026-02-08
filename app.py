from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv
import logging

# load local .env for development (no effect in Azure App Service)
load_dotenv()

logging.basicConfig(level=logging.INFO)
from flask import Flask, render_template, request, redirect, session, flash
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


# Ensure admins table exists and seed an initial admin if none
def ensure_admin_table():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
        """
    )
    db.commit()

    cur.execute("SELECT COUNT(*) FROM admins")
    count = cur.fetchone()[0]
    if count == 0:
        # seed a default admin for initial setup; change password after first login
        cur.execute("INSERT INTO admins (email, password) VALUES (?, ?)", ("admin@college.com", "admin123"))
        db.commit()

ensure_admin_table()


# helper to provide staff list to templates
def get_staff_list():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM staff")
    return cur.fetchall()


def get_students_list():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, email FROM students")
    return cur.fetchall()


@app.context_processor
def inject_helpers():
    return {"get_staff_list": get_staff_list, "get_students_list": get_students_list}


@app.route('/admin/create_staff', methods=['POST'])
def admin_create_staff():
    if session.get('role') != 'admin':
        return redirect('/login')

    email = request.form.get('email')
    password = request.form.get('password')
    if not email or not password:
        return "email and password required", 400

    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO staff (email, password) VALUES (?, ?)", (email, password))
    db.commit()

    return redirect('/dashboard')


@app.route('/admin/staff/<int:staff_id>', methods=['GET', 'POST'])
def admin_staff_detail(staff_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        if request.form.get('delete'):
            cur.execute('DELETE FROM staff WHERE id=?', (staff_id,))
            db.commit()
            return redirect('/dashboard')

        email = request.form.get('email')
        password = request.form.get('password')
        if password:
            cur.execute('UPDATE staff SET email=?, password=? WHERE id=?', (email, password, staff_id))
        else:
            cur.execute('UPDATE staff SET email=? WHERE id=?', (email, staff_id))
        db.commit()
        return redirect(f'/admin/staff/{staff_id}')

    staff = cur.execute('SELECT id, email FROM staff WHERE id=?', (staff_id,)).fetchone()
    return render_template('admin/staff_detail.html', staff=staff)


@app.route('/admin/student/<int:student_id>', methods=['GET', 'POST'])
def admin_student_detail(student_id):
    if session.get('role') != 'admin':
        return redirect('/login')

    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        if request.form.get('delete'):
            cur.execute('DELETE FROM students WHERE id=?', (student_id,))
            db.commit()
            return redirect('/dashboard')

        email = request.form.get('email')
        password = request.form.get('password')
        if password:
            cur.execute('UPDATE students SET email=?, password=? WHERE id=?', (email, password, student_id))
        else:
            cur.execute('UPDATE students SET email=? WHERE id=?', (email, student_id))
        db.commit()
        return redirect(f'/admin/student/{student_id}')

    student = cur.execute('SELECT id, email FROM students WHERE id=?', (student_id,)).fetchone()
    return render_template('admin/student_detail.html', student=student)


@app.route('/admin/manage_staffs')
def admin_manage_staffs():
    if session.get('role') != 'admin':
        return redirect('/login')
    staff_list = get_staff_list()
    return render_template('admin/manage_staffs.html', staff_list=staff_list)


@app.route('/admin/manage_students')
def admin_manage_students():
    if session.get('role') != 'admin':
        return redirect('/login')
    students_list = get_students_list()
    return render_template('admin/manage_students.html', students_list=students_list)

@app.route("/")
def home():
    # If already authenticated, send user to their dashboard instead of showing public home
    if "role" in session:
        return redirect("/dashboard")
    return render_template("home.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    # Prevent logged-in users from seeing the login page
    if request.method == "GET" and "role" in session:
        return redirect("/dashboard")

    if request.method == "POST":
        role = request.form["role"]
        email = request.form["email"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()

        if role == "staff":
            cur.execute("SELECT * FROM staff WHERE email=? AND password=?", (email, password))
        elif role == "admin":
            cur.execute("SELECT * FROM admins WHERE email=? AND password=?", (email, password))
        else:
            cur.execute("SELECT * FROM students WHERE email=? AND password=?", (email, password))

        user = cur.fetchone()

        if user:
            session["role"] = role
            session["email"] = email
            flash('Successfully logged in', 'success')
            return redirect("/dashboard")
        else:
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('login.html'), 401

    return render_template('login.html')


@app.after_request
def add_no_cache_headers(response):
    # Prevent caching of HTML pages so back-button after logout won't show protected content
    try:
        ctype = response.headers.get('Content-Type', '')
        if ctype and ctype.split(';')[0].strip() == 'text/html':
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
    except Exception:
        pass
    return response

@app.route("/dashboard")
def dashboard():
    if "role" not in session:
        return redirect("/login")
    if session["role"] == "staff":
        return render_template('staff/dashboard.html')
    elif session["role"] == "admin":
        return render_template('admin/dashboard.html')
    else:
        return render_template('student/dashboard.html')


@app.route("/create_student", methods=["POST"])
def create_student():
    # Allow staff or admin to create student accounts
    role = session.get("role")
    if role not in ("staff", "admin"):
        return redirect("/login")

    email = request.form.get("email")
    password = request.form.get("password")
    # Admins may set mentor_email explicitly; staff will be assigned as mentor
    # Admin-created students are not assigned a mentor by default
    if role == "admin":
        mentor_email = None
    else:
        mentor_email = session.get("email")

    if not email or not password:
        return "Email and password required", 400

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO students (email, password, mentor_email) VALUES (?, ?, ?)",
        (email, password, mentor_email),
    )
    db.commit()

    return redirect("/dashboard")
    
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if session.get("role") != "student":
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("file")
        cert_type = request.form.get("cert_type")

        # quick environment checks to give clearer errors
        if not container:
            logging.error("AZURE_CONTAINER environment variable is not set")
            return "Server misconfigured: AZURE_CONTAINER not set", 500

        if not os.getenv("AZURE_STORAGE_ACCOUNT"):
            logging.error("AZURE_STORAGE_ACCOUNT environment variable is not set")
            return "Server misconfigured: AZURE_STORAGE_ACCOUNT not set", 500

        if not file or not getattr(file, 'filename', None):
            return "No file provided", 400

        blob_client = blob_service.get_blob_client(container=container, blob=file.filename)
        blob_client.upload_blob(file, overwrite=True)

        db = get_db()
        db.execute(
            "INSERT INTO documents (student_email, filename, cert_type) VALUES (?, ?, ?)",
            (session["email"], file.filename, cert_type)
        )
        db.commit()

        return "Uploaded successfully"

    return render_template('student/upload.html')

@app.route("/documents")
def documents():
    if session.get("role") != "staff":
        return redirect("/login")

    db = get_db()
    docs = db.execute("SELECT * FROM documents").fetchall()

    return render_template('staff/documents.html', docs=docs)


@app.route('/staff/manage_students')
def staff_manage_students():
    if session.get('role') != 'staff':
        return redirect('/login')

    db = get_db()
    mentor = session.get('email')
    # show all students and their mentor (if any) so staff can map themselves
    students = db.execute('SELECT id, email, mentor_email FROM students ORDER BY email').fetchall()

    return render_template('staff/manage_students.html', students=students, mentor=mentor)


@app.route('/staff/map_student/<int:student_id>', methods=['POST'])
def staff_map_student(student_id):
    if session.get('role') != 'staff':
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    row = cur.execute('SELECT mentor_email FROM students WHERE id=?', (student_id,)).fetchone()
    if not row:
        flash('Student not found', 'danger')
        return redirect('/staff/manage_students')

    current = row[0]
    if current is None:
        cur.execute('UPDATE students SET mentor_email=? WHERE id=?', (session.get('email'), student_id))
        db.commit()
        flash('Student mapped to you', 'success')
    else:
        flash('Student already assigned', 'warning')

    return redirect('/staff/manage_students')


@app.route('/staff/unmap_student/<int:student_id>', methods=['POST'])
def staff_unmap_student(student_id):
    if session.get('role') != 'staff':
        return redirect('/login')

    db = get_db()
    cur = db.cursor()
    row = cur.execute('SELECT mentor_email FROM students WHERE id=?', (student_id,)).fetchone()
    if not row:
        flash('Student not found', 'danger')
        return redirect('/staff/manage_students')

    current = row[0]
    if current != session.get('email'):
        flash('You are not the mentor of this student', 'danger')
        return redirect('/staff/manage_students')

    cur.execute('UPDATE students SET mentor_email=NULL WHERE id=?', (student_id,))
    db.commit()
    flash('Student unmapped successfully', 'success')
    return redirect('/staff/manage_students')


@app.route('/staff/manage_documents')
def staff_manage_documents():
    if session.get('role') != 'staff':
        return redirect('/login')

    db = get_db()
    mentor = session.get('email')
    docs = db.execute('''
        SELECT d.id, d.student_email, d.filename, d.cert_type, d.uploaded_at
        FROM documents d
        JOIN students s ON s.email = d.student_email
        WHERE s.mentor_email = ?
        ORDER BY d.uploaded_at DESC
    ''', (mentor,)).fetchall()

    return render_template('staff/manage_documents.html', docs=docs)


@app.route("/my-documents")
def my_documents():
    if session.get("role") != "student":
        return redirect("/login")

    db = get_db()
    docs = db.execute("SELECT * FROM documents WHERE student_email=?", (session["email"],)).fetchall()

    return render_template('student/documents.html', docs=docs)


@app.route("/profile")
def profile():
    if "role" not in session:
        return redirect("/login")

    db = get_db()
    role = session.get("role")
    user = None
    if role == "student":
        user = db.execute("SELECT email, mentor_email FROM students WHERE email=?", (session.get("email"),)).fetchone()
    else:
        user = db.execute("SELECT email FROM staff WHERE email=?", (session.get("email"),)).fetchone()

    return render_template('shared/profile.html', role=role, user=user)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run()
