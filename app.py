from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv
import logging

# load local .env for development (no effect in Azure App Service)
load_dotenv()

logging.basicConfig(level=logging.INFO)
from flask import Flask, render_template, request, redirect, session, flash, Response
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
    return {
        "get_staff_list": get_staff_list,
        "get_students_list": get_students_list,
        "AZURE_STORAGE_ACCOUNT": os.getenv('AZURE_STORAGE_ACCOUNT'),
        "AZURE_CONTAINER": container,
    }


def ensure_verification_columns():
    db = get_db()
    cur = db.cursor()
    # add columns if they don't exist
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN verified INTEGER DEFAULT 0")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN verifier TEXT")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE documents ADD COLUMN verified_at TIMESTAMP")
    except Exception:
        pass
    db.commit()


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


@app.route('/admin/students/template')
def admin_students_template():
    if session.get('role') != 'admin':
        return redirect('/login')
    csv_content = 'email,password\n'
    return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=students_template.csv'})


@app.route('/admin/students/import', methods=['POST'])
def admin_students_import():
    if session.get('role') != 'admin':
        return redirect('/login')

    file = request.files.get('file')
    if not file or not getattr(file, 'filename', None):
        flash('No file provided', 'danger')
        return redirect('/admin/manage_students')

    import io, csv

    try:
        stream = io.StringIO(file.stream.read().decode('utf-8'))
    except Exception:
        flash('Failed to read uploaded file. Ensure it is a UTF-8 CSV.', 'danger')
        return redirect('/admin/manage_students')

    reader = csv.DictReader(stream)
    db = get_db()
    cur = db.cursor()
    added = 0
    for row in reader:
        email = row.get('email') or row.get('Email') or row.get('EMAIL')
        password = row.get('password') or row.get('Password') or row.get('PASSWORD')
        if not email or not password:
            continue
        try:
            cur.execute("INSERT INTO students (email, password, mentor_email) VALUES (?, ?, ?)", (email.strip(), password.strip(), None))
            added += 1
        except Exception as e:
            logging.warning(f"Skipping {email}: {e}")
    db.commit()
    flash(f'Imported {added} students', 'success')
    return redirect('/admin/manage_students')


@app.route('/admin/staffs/template')
def admin_staffs_template():
    if session.get('role') != 'admin':
        return redirect('/login')
    csv_content = 'email,password\n'
    return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=staffs_template.csv'})


@app.route('/admin/staffs/import', methods=['POST'])
def admin_staffs_import():
    if session.get('role') != 'admin':
        return redirect('/login')

    file = request.files.get('file')
    if not file or not getattr(file, 'filename', None):
        flash('No file provided', 'danger')
        return redirect('/admin/manage_staffs')

    import io, csv

    try:
        stream = io.StringIO(file.stream.read().decode('utf-8'))
    except Exception:
        flash('Failed to read uploaded file. Ensure it is a UTF-8 CSV.', 'danger')
        return redirect('/admin/manage_staffs')

    reader = csv.DictReader(stream)
    db = get_db()
    cur = db.cursor()
    added = 0
    for row in reader:
        email = row.get('email') or row.get('Email') or row.get('EMAIL')
        password = row.get('password') or row.get('Password') or row.get('PASSWORD')
        if not email or not password:
            continue
        try:
            cur.execute("INSERT INTO staff (email, password) VALUES (?, ?)", (email.strip(), password.strip()))
            added += 1
        except Exception as e:
            logging.warning(f"Skipping {email}: {e}")
    db.commit()
    flash(f'Imported {added} staff users', 'success')
    return redirect('/admin/manage_staffs')

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
    # optional student filter via query param
    student_filter = request.args.get('student')
    docs = db.execute('''
        SELECT d.id, d.student_email, d.filename, d.cert_type, d.uploaded_at
        FROM documents d
        JOIN students s ON s.email = d.student_email
        WHERE s.mentor_email = ?
        ''' + (" AND d.student_email = ?" if student_filter else "") + '''
        ORDER BY d.uploaded_at DESC
    ''', (mentor,) if not student_filter else (mentor, student_filter)).fetchall()

    # Simple analytics (lightweight "ML-like" insights): per-student upload counts,
    # cert-type distributions, and basic scoring (uploads vs expected).
    if student_filter:
        students = db.execute('SELECT id, email FROM students WHERE mentor_email = ? AND email = ?', (mentor, student_filter)).fetchall()
    else:
        students = db.execute('SELECT id, email FROM students WHERE mentor_email = ?', (mentor,)).fetchall()
    expected_per_student = 3
    students_stats = []
    total_uploads = 0
    cert_type_agg = {}

    for s in students:
        email = s[1]
        cur = db.execute('SELECT COUNT(*), GROUP_CONCAT(cert_type) FROM documents WHERE student_email = ?', (email,))
        row = cur.fetchone()
        uploads = row[0] if row and row[0] is not None else 0
        cert_types_concat = row[1] or ''
        # build cert-type counts
        cert_counts = {}
        if cert_types_concat:
            for ct in cert_types_concat.split(','):
                ct = (ct or '').strip()
                if not ct:
                    continue
                cert_counts[ct] = cert_counts.get(ct, 0) + 1
                cert_type_agg[ct] = cert_type_agg.get(ct, 0) + 1

        score = int(min(100, (uploads / expected_per_student) * 100)) if expected_per_student > 0 else 0
        students_stats.append({'email': email, 'uploads': uploads, 'cert_counts': cert_counts, 'score': score})
        total_uploads += uploads

    avg_uploads = (total_uploads / len(students)) if students else 0
    # top cert types
    top_cert_types = sorted(cert_type_agg.items(), key=lambda x: x[1], reverse=True)[:5]

    # Simple file-based summarization (keywords from filenames, recent uploads)
    import re
    stopwords = set(['the','and','of','in','a','an','for','to','on','by','with','cert','certificate','doc','document','pdf','jpg','png'])

    keyword_counts = {}
    recent_uploads = []
    per_student_latest = {}

    for d in docs:
        filename = d[2] or ''
        email = d[1]
        uploaded_at = d[4]
        # recent uploads list (docs already ordered desc)
        if len(recent_uploads) < 5:
            recent_uploads.append({'filename': filename, 'student': email, 'uploaded_at': uploaded_at})

        # per-student latest
        if email not in per_student_latest:
            per_student_latest[email] = {'filename': filename, 'uploaded_at': uploaded_at}

        # extract keywords from filename
        parts = re.split(r"[^A-Za-z0-9]+", filename.lower())
        for p in parts:
            if not p or p in stopwords or len(p) < 2:
                continue
            keyword_counts[p] = keyword_counts.get(p, 0) + 1

    top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    analytics = {
        'total_students': len(students),
        'total_uploads': total_uploads,
        'avg_uploads': round(avg_uploads, 2),
        'top_cert_types': top_cert_types,
        'students_stats': students_stats,
        'summary': {
            'top_keywords': top_keywords,
            'recent_uploads': recent_uploads,
            'per_student_latest': per_student_latest,
        }
    }

    return render_template('staff/manage_documents.html', docs=docs, analytics=analytics)


@app.route('/documents/download/<int:doc_id>')
def documents_download(doc_id):
    if session.get('role') not in ('staff', 'admin', 'student'):
        return redirect('/login')

    db = get_db()
    row = db.execute('SELECT filename FROM documents WHERE id=?', (doc_id,)).fetchone()
    if not row:
        flash('Document not found', 'danger')
        return redirect('/dashboard')

    filename = row[0]
    if not container:
        flash('Server not configured for blob container', 'danger')
        return redirect('/dashboard')

    try:
        blob_client = blob_service.get_blob_client(container=container, blob=filename)
        stream = blob_client.download_blob().readall()
        return Response(stream, mimetype='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    except Exception as e:
        logging.exception('Failed to download blob')
        flash('Failed to download file', 'danger')
        return redirect('/dashboard')


@app.route('/documents/view/<int:doc_id>')
def documents_view(doc_id):
    if session.get('role') not in ('staff', 'admin', 'student'):
        return redirect('/login')

    db = get_db()
    row = db.execute('SELECT filename FROM documents WHERE id=?', (doc_id,)).fetchone()
    if not row:
        flash('Document not found', 'danger')
        return redirect('/dashboard')

    filename = row[0]
    # Prefer direct blob URL for browser viewing
    account = os.getenv('AZURE_STORAGE_ACCOUNT')
    if account and container:
        url = f"https://{account}.blob.core.windows.net/{container}/{filename}"
        return redirect(url)
    else:
        return redirect('/documents')


@app.route('/documents/verify/<int:doc_id>', methods=['POST'])
def documents_verify(doc_id):
    if session.get('role') not in ('staff', 'admin'):
        return redirect('/login')

    ensure_verification_columns()
    db = get_db()
    cur = db.cursor()
    verifier = session.get('email')
    try:
        cur.execute('UPDATE documents SET verified=1, verifier=?, verified_at=CURRENT_TIMESTAMP WHERE id=?', (verifier, doc_id))
        db.commit()
        flash('Document verified', 'success')
    except Exception:
        logging.exception('Failed to mark document verified')
        flash('Failed to verify document', 'danger')

    return redirect(request.referrer or '/dashboard')


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
