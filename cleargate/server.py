#!/usr/bin/env python3
"""ClearGate - Student Clearance Portal.

A zero-dependency web server (Python 3.9+) backed by a brand-new SQLite database
(cleargate.db, created on first run).

    python3 server.py                      start the portal at http://localhost:8000
    python3 server.py add-student ...      add a student (all offices start as "pending")
    python3 server.py set-status ...       update a student's clearance at an office
    python3 server.py log                  show the newest activity the database has gathered
"""
import argparse
import getpass
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CLEARGATE_DB", BASE / "cleargate.db"))
STATIC = BASE / "static"
COOKIE = "cleargate_session"
STATUSES = ("approved", "pending", "action")
SESSION_HOURS = 24            # normal login
REMEMBER_DAYS = 30            # "Remember me"
CODE_MINUTES = 10             # password-reset code lifetime
MIN_PASSWORD = 8

OFFICES = [
    ("Registrar", "files"),
    ("Accounting", "wallet"),
    ("Library", "book"),
    ("Guidance Office", "heart"),
    ("Dean's Office", "cap"),
    ("Property Custodian", "box"),
]

DEMO_STUDENT = dict(
    student_no="2023-00123",
    email="ariel.tapnio@example.com",
    name="Ariel Tapnio",
    course_year="3rd Year, BSCS",
    academic_year="A.Y 2026 - 2027",
    password="ClearGate#2026",
)

# office, status, card summary, table detail, checklist title, checklist description
DEMO_CLEARANCE = [
    ("Registrar", "approved", "(All Records verified)", "Records verified, form submitted",
     "Records verified, form submitted", "Registrar has already cleared your account."),
    ("Accounting", "pending", "Review, balance $20.00", "Review balance $20.00",
     "Review balance $20.00", "Review your balance with Accounting to resolve the pending clearance."),
    ("Library", "action", "(1 unreturned book)", "1 unreturned book",
     "Return 1 unreturned book", "Library is waiting for the book to be returned before your account can be cleared."),
    ("Guidance Office", "approved", "(Cleared!)", "No issues, cleared",
     "No issues, cleared", "Guidance Office has already cleared your account."),
    ("Dean's Office", "approved", "(Cleared)", "Academic stand okay",
     "Academic stand okay", "Dean's Office has already cleared your account."),
    ("Property Custodian", "approved", "(Approved)", "No liabilities",
     "No liabilities", "Property Custodian has already cleared your account."),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY,
    student_no    TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT NOT NULL,
    course_year   TEXT NOT NULL,
    academic_year TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS offices (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    icon TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clearance (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    office_id   INTEGER NOT NULL REFERENCES offices(id),
    status      TEXT NOT NULL CHECK (status IN ('approved','pending','action')),
    summary     TEXT NOT NULL,
    detail      TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (student_id, office_id)
);
CREATE TABLE IF NOT EXISTS clearance_history (
    id           INTEGER PRIMARY KEY,
    clearance_id INTEGER NOT NULL REFERENCES clearance(id) ON DELETE CASCADE,
    old_status   TEXT,
    new_status   TEXT NOT NULL,
    note         TEXT,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
    id         INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    code_hash  TEXT NOT NULL,
    token_hash TEXT,
    attempts   INTEGER NOT NULL DEFAULT 0,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id         INTEGER PRIMARY KEY,
    identifier TEXT NOT NULL,
    success    INTEGER NOT NULL,
    ip         TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity_log (
    id           INTEGER PRIMARY KEY,
    student_id   INTEGER REFERENCES students(id) ON DELETE SET NULL,
    clearance_id INTEGER,
    action       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(identifier, created_at);
CREATE INDEX IF NOT EXISTS idx_activity ON activity_log(student_id, created_at);
"""


# --------------------------------------------------------------------------- helpers
def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def later(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def hash_pw(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"


def check_pw(password, stored):
    salt, digest = stored.split("$")
    new = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(new.hex(), digest)


def default_text(office, status, detail):
    if status == "approved":
        return detail, f"{office} has already cleared your account."
    if status == "pending":
        return detail, f"Review your records with {office} to resolve the pending clearance."
    return detail, f"{office} needs action from you before your account can be cleared."


def set_clearance(con, student_id, office_id, status, summary, detail,
                  title=None, description=None, note=None):
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    office = con.execute("SELECT name FROM offices WHERE id=?", (office_id,)).fetchone()["name"]
    d_title, d_desc = default_text(office, status, detail)
    title, description = title or d_title, description or d_desc
    ts = now()
    old = con.execute("SELECT id, status FROM clearance WHERE student_id=? AND office_id=?",
                      (student_id, office_id)).fetchone()
    if old:
        con.execute("""UPDATE clearance SET status=?, summary=?, detail=?, title=?, description=?,
                       updated_at=? WHERE id=?""",
                    (status, summary, detail, title, description, ts, old["id"]))
        cid, prev = old["id"], old["status"]
    else:
        cur = con.execute("""INSERT INTO clearance(student_id, office_id, status, summary, detail,
                             title, description, updated_at) VALUES (?,?,?,?,?,?,?,?)""",
                          (student_id, office_id, status, summary, detail, title, description, ts))
        cid, prev = cur.lastrowid, None
    con.execute("""INSERT INTO clearance_history(clearance_id, old_status, new_status, note, created_at)
                   VALUES (?,?,?,?,?)""", (cid, prev, status, note, ts))
    return cid


def init_db():
    with conn() as con:
        con.executescript(SCHEMA)
        for name, icon in OFFICES:
            con.execute("INSERT OR IGNORE INTO offices(name, icon) VALUES (?,?)", (name, icon))
        empty = not con.execute("SELECT 1 FROM students LIMIT 1").fetchone()
        if empty and os.environ.get("CLEARGATE_SEED", "1") != "0":
            d = DEMO_STUDENT
            cur = con.execute("""INSERT INTO students(student_no, email, name, course_year,
                                 academic_year, password_hash, created_at) VALUES (?,?,?,?,?,?,?)""",
                              (d["student_no"], d["email"], d["name"], d["course_year"],
                               d["academic_year"], hash_pw(d["password"]), now()))
            for office, status, summary, detail, title, desc in DEMO_CLEARANCE:
                oid = con.execute("SELECT id FROM offices WHERE name=?", (office,)).fetchone()["id"]
                set_clearance(con, cur.lastrowid, oid, status, summary, detail, title, desc,
                              note="demo data")
            print(f"[ClearGate] Created demo student. Sign in with  {d['student_no']}  or  "
                  f"{d['email']}  /  {d['password']}")
            print("[ClearGate] Remove it for real use: set CLEARGATE_SEED=0 before the first run, "
                  "or delete cleargate.db.")


def send_reset_code(email, code):
    """Delivery hook. No email service is configured, so the code is printed to this console.
    Replace the body with SMTP / an email API call to send real emails."""
    print(f"[ClearGate] Password reset code for {email}: {code}  (valid {CODE_MINUTES} min)", flush=True)


class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ClearGate/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---- responses
    def _headers(self, code, ctype, length, cookie=None, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def send_json(self, code, obj, cookie=None):
        body = json.dumps(obj).encode()
        self._headers(code, "application/json", len(body), cookie, {"Cache-Control": "no-store"})
        self.wfile.write(body)

    def redirect(self, where):
        self._headers(302, "text/plain", 0, extra={"Location": where, "Cache-Control": "no-store"})

    # ---- session helpers
    def student(self, con):
        try:
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
        except Exception:
            return None
        if not morsel:
            return None
        return con.execute("""SELECT s.* FROM sessions x JOIN students s ON s.id = x.student_id
                              WHERE x.token_hash=? AND x.expires_at>?""",
                           (sha(morsel.value), now())).fetchone()

    def new_session(self, con, student_id, remember=False):
        token = secrets.token_urlsafe(32)
        expires = later(days=REMEMBER_DAYS) if remember else later(hours=SESSION_HOURS)
        con.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
        con.execute("INSERT INTO sessions VALUES (?,?,?,?)", (sha(token), student_id, now(), expires))
        cookie = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax"
        if remember:
            cookie += f"; Max-Age={REMEMBER_DAYS * 86400}"
        if os.environ.get("CLEARGATE_SECURE") == "1":
            cookie += "; Secure"
        return cookie

    def read_json(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ApiError(415, "Expected JSON.")
        size = int(self.headers.get("Content-Length") or 0)
        if size > 10_000:
            raise ApiError(413, "Request too large.")
        try:
            data = json.loads(self.rfile.read(size) or b"{}")
        except ValueError:
            raise ApiError(400, "Invalid JSON.")
        if not isinstance(data, dict):
            raise ApiError(400, "Invalid JSON.")
        return data

    # ---- routing
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        return self.static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("POST", path)
        self.send_json(405, {"error": "Method not allowed."})

    def static(self, path):
        if path in ("/", "/index.html", "/portal"):
            with conn() as con:
                user = self.student(con)
            if path == "/portal" and not user:
                return self.redirect("/")
            if path != "/portal" and user:
                return self.redirect("/portal")
            path = "/portal.html" if path == "/portal" else "/login.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            body = b"Not found"
            return self._headers(404, "text/plain", len(body)) or self.wfile.write(body)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8" if ctype.startswith("text/") else ""
        body = target.read_bytes()
        self._headers(200, ctype, len(body), extra={"Cache-Control": "no-cache"})
        self.wfile.write(body)

    def api(self, method, path):
        try:
            with conn() as con:
                route = {
                    ("POST", "/api/login"): self.r_login,
                    ("POST", "/api/signup"): self.r_signup,
                    ("POST", "/api/logout"): self.r_logout,
                    ("GET", "/api/me"): self.r_me,
                    ("GET", "/api/clearance"): self.r_clearance,
                    ("POST", "/api/activity"): self.r_activity,
                    ("POST", "/api/forgot/request"): self.r_forgot_request,
                    ("POST", "/api/forgot/verify"): self.r_forgot_verify,
                    ("POST", "/api/forgot/reset"): self.r_forgot_reset,
                }.get((method, path))
                if not route:
                    raise ApiError(404, "Not found.")
                return route(con)
        except ApiError as e:
            self.send_json(e.code, {"error": e.msg})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "Something went wrong on the server."})

    def need_student(self, con):
        user = self.student(con)
        if not user:
            raise ApiError(401, "Please sign in.")
        return user

    # ---- auth routes
    def r_signup(self, con):
        b = self.read_json()
        student_no = str(b.get("student_no", "")).strip()
        email = str(b.get("email", "")).strip()
        name = str(b.get("name", "")).strip()
        course_year = str(b.get("course_year", "")).strip()
        academic_year = str(b.get("academic_year", "")).strip()
        password = str(b.get("password", ""))

        if not all((student_no, email, name, course_year, academic_year, password)):
            raise ApiError(400, "Complete all fields to create your account.")
        if (len(student_no) > 40 or len(email) > 120 or len(name) > 120
                or len(course_year) > 120 or len(academic_year) > 40):
            raise ApiError(400, "One or more fields are too long.")
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ApiError(400, "Enter a valid email address.")
        if len(password) < MIN_PASSWORD or len(password) > 200:
            raise ApiError(400, f"Use a password between {MIN_PASSWORD} and 200 characters.")
        if con.execute("SELECT 1 FROM students WHERE student_no=? OR email=?",
                       (student_no, email)).fetchone():
            raise ApiError(409, "That Student ID or email is already registered.")

        cur = con.execute("""INSERT INTO students(student_no, email, name, course_year,
                             academic_year, password_hash, created_at) VALUES (?,?,?,?,?,?,?)""",
                          (student_no, email, name, course_year, academic_year,
                           hash_pw(password), now()))
        student_id = cur.lastrowid
        for office in con.execute("SELECT id, name FROM offices ORDER BY id").fetchall():
            set_clearance(con, student_id, office["id"], "pending", "Awaiting review",
                          "Awaiting review", f"Awaiting review from {office['name']}",
                          f"{office['name']} has not reviewed your account yet.",
                          note="student registered")
        con.execute("INSERT INTO activity_log(student_id, action, created_at) VALUES (?,?,?)",
                    (student_id, "signup", now()))
        cookie = self.new_session(con, student_id)
        self.send_json(201, {"ok": True}, cookie)

    def r_login(self, con):
        b = self.read_json()
        ident = str(b.get("identifier", "")).strip()[:120]
        password = str(b.get("password", ""))[:200]
        if not ident or not password:
            raise ApiError(400, "Enter your Student ID or email and your password.")
        failures = con.execute("""SELECT COUNT(*) FROM login_attempts WHERE identifier=? COLLATE NOCASE
                                  AND success=0 AND created_at>?""",
                               (ident, later(minutes=-15))).fetchone()[0]
        if failures >= 5:
            raise ApiError(429, "Too many failed attempts. Try again in 15 minutes.")
        user = con.execute("SELECT * FROM students WHERE student_no=? OR email=?", (ident, ident)).fetchone()
        ok = check_pw(password, user["password_hash"]) if user else (hash_pw(password) and False)
        con.execute("INSERT INTO login_attempts(identifier, success, ip, created_at) VALUES (?,?,?,?)",
                    (ident, int(ok), self.client_address[0], now()))
        if not ok:
            con.commit()
            raise ApiError(401, "Incorrect Student ID / email or password.")
        cookie = self.new_session(con, user["id"], bool(b.get("remember")))
        con.execute("INSERT INTO activity_log(student_id, action, created_at) VALUES (?,?,?)",
                    (user["id"], "login", now()))
        self.send_json(200, {"ok": True}, cookie)

    def r_logout(self, con):
        try:
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(COOKIE)
        except Exception:
            morsel = None
        if morsel:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (sha(morsel.value),))
        self.send_json(200, {"ok": True}, f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def r_me(self, con):
        u = self.need_student(con)
        self.send_json(200, {"name": u["name"], "student_no": u["student_no"]})

    # ---- clearance data
    def r_clearance(self, con):
        u = self.need_student(con)
        rows = con.execute("""SELECT c.id, o.name AS office, o.icon, c.status, c.summary, c.detail,
                                     c.title, c.description, c.updated_at
                              FROM clearance c JOIN offices o ON o.id = c.office_id
                              WHERE c.student_id=? ORDER BY o.id""", (u["id"],)).fetchall()
        self.send_json(200, {
            "student": {"name": u["name"], "student_no": u["student_no"],
                        "course_year": u["course_year"], "academic_year": u["academic_year"]},
            "items": [dict(r) for r in rows],
        })

    def r_activity(self, con):
        u = self.need_student(con)
        b = self.read_json()
        action = b.get("action")
        if action not in ("view_details", "contact_office"):
            raise ApiError(400, "Unknown action.")
        cid = b.get("clearance_id")
        owns = con.execute("SELECT 1 FROM clearance WHERE id=? AND student_id=?", (cid, u["id"])).fetchone()
        if not owns:
            raise ApiError(404, "Not found.")
        con.execute("INSERT INTO activity_log(student_id, clearance_id, action, created_at) VALUES (?,?,?,?)",
                    (u["id"], cid, action, now()))
        self.send_json(200, {"ok": True})

    # ---- forgot password: request code -> verify code -> set new password
    def r_forgot_request(self, con):
        email = str(self.read_json().get("email", "")).strip()[:120]
        user = con.execute("SELECT * FROM students WHERE email=?", (email,)).fetchone()
        if user:
            recent = con.execute("SELECT COUNT(*) FROM password_resets WHERE student_id=? AND created_at>?",
                                 (user["id"], later(hours=-1))).fetchone()[0]
            if recent < 3:
                code = f"{secrets.randbelow(10 ** 6):06d}"
                con.execute("""INSERT INTO password_resets(student_id, code_hash, created_at, expires_at)
                               VALUES (?,?,?,?)""",
                            (user["id"], hash_pw(code), now(), later(minutes=CODE_MINUTES)))
                con.commit()
                send_reset_code(user["email"], code)
        # Same answer whether or not the email exists, so accounts can't be probed.
        self.send_json(200, {"ok": True})

    def r_forgot_verify(self, con):
        b = self.read_json()
        email = str(b.get("email", "")).strip()[:120]
        code = str(b.get("code", "")).strip()[:12]
        bad = ApiError(400, "That code is invalid or has expired.")
        user = con.execute("SELECT id FROM students WHERE email=?", (email,)).fetchone()
        if not user:
            raise bad
        r = con.execute("""SELECT * FROM password_resets WHERE student_id=? AND used=0 AND expires_at>?
                           ORDER BY id DESC LIMIT 1""", (user["id"], now())).fetchone()
        if not r or r["attempts"] >= 5:
            raise bad
        con.execute("UPDATE password_resets SET attempts=attempts+1 WHERE id=?", (r["id"],))
        if not check_pw(code, r["code_hash"]):
            con.commit()
            raise bad
        token = secrets.token_urlsafe(32)
        con.execute("UPDATE password_resets SET token_hash=? WHERE id=?", (sha(token), r["id"]))
        self.send_json(200, {"ok": True, "token": token})

    def r_forgot_reset(self, con):
        b = self.read_json()
        token = str(b.get("token", ""))[:100]
        password = str(b.get("password", ""))
        if len(password) < MIN_PASSWORD or len(password) > 200:
            raise ApiError(400, f"Use at least {MIN_PASSWORD} characters for your new password.")
        r = con.execute("""SELECT * FROM password_resets WHERE token_hash=? AND used=0 AND expires_at>?""",
                        (sha(token), now())).fetchone() if token else None
        if not r:
            raise ApiError(400, "This reset link has expired. Please start again.")
        con.execute("UPDATE students SET password_hash=? WHERE id=?", (hash_pw(password), r["student_id"]))
        con.execute("UPDATE password_resets SET used=1 WHERE id=?", (r["id"],))
        con.execute("DELETE FROM sessions WHERE student_id=?", (r["student_id"],))
        con.execute("INSERT INTO activity_log(student_id, action, created_at) VALUES (?,?,?)",
                    (r["student_id"], "password_reset", now()))
        cookie = self.new_session(con, r["student_id"])
        self.send_json(200, {"ok": True}, cookie)


# --------------------------------------------------------------------------- CLI
def find_student(con, key):
    s = con.execute("SELECT * FROM students WHERE student_no=? OR email=?", (key, key)).fetchone()
    if not s:
        sys.exit(f"No student found for '{key}'.")
    return s


def cmd_serve(a):
    init_db()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"[ClearGate] Database: {DB_PATH}")
    print(f"[ClearGate] Running at http://{'localhost' if a.host in ('127.0.0.1', '0.0.0.0') else a.host}:{a.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[ClearGate] Stopped.")


def cmd_add_student(a):
    init_db()
    password = a.password or getpass.getpass("Password for the new student: ")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"Password must be at least {MIN_PASSWORD} characters.")
    with conn() as con:
        try:
            cur = con.execute("""INSERT INTO students(student_no, email, name, course_year, academic_year,
                                 password_hash, created_at) VALUES (?,?,?,?,?,?,?)""",
                              (a.student_no, a.email, a.name, a.course, a.year, hash_pw(password), now()))
        except sqlite3.IntegrityError:
            sys.exit("That student number or email already exists.")
        for o in con.execute("SELECT id, name FROM offices ORDER BY id").fetchall():
            set_clearance(con, cur.lastrowid, o["id"], "pending", "Awaiting review", "Awaiting review",
                          f"Awaiting review from {o['name']}", f"{o['name']} has not reviewed your account yet.",
                          note="student added")
    print(f"Added {a.name} ({a.student_no}); all {len(OFFICES)} offices are pending.")


def cmd_set_status(a):
    init_db()
    with conn() as con:
        s = find_student(con, a.student)
        o = con.execute("SELECT * FROM offices WHERE name=? COLLATE NOCASE", (a.office,)).fetchone()
        if not o:
            sys.exit("Unknown office. Choose from: " + ", ".join(n for n, _ in OFFICES))
        detail = a.detail or {"approved": "Cleared", "pending": "Under review", "action": "Action required"}[a.status]
        summary = a.summary or (f"({detail})" if a.status == "approved" else detail)
        set_clearance(con, s["id"], o["id"], a.status, summary, detail, note=a.note or "set via CLI")
    print(f"{s['name']} - {o['name']}: {a.status} ({detail})")


def cmd_log(a):
    init_db()
    with conn() as con:
        print("== Recent activity ==")
        for r in con.execute("""SELECT l.created_at, COALESCE(s.name,'(deleted)') AS who, l.action,
                                       COALESCE(o.name,'') AS office
                                FROM activity_log l LEFT JOIN students s ON s.id=l.student_id
                                LEFT JOIN clearance c ON c.id=l.clearance_id
                                LEFT JOIN offices o ON o.id=c.office_id
                                ORDER BY l.id DESC LIMIT ?""", (a.limit,)):
            print(f"{r['created_at']}  {r['who']:<20} {r['action']:<15} {r['office']}")
        print("\n== Recent sign-in attempts ==")
        for r in con.execute("SELECT * FROM login_attempts ORDER BY id DESC LIMIT ?", (a.limit,)):
            print(f"{r['created_at']}  {r['identifier']:<28} {'ok' if r['success'] else 'FAILED':<7} {r['ip']}")
        print("\n== Recent status changes ==")
        for r in con.execute("""SELECT h.created_at, s.name, o.name AS office, h.old_status, h.new_status, h.note
                                FROM clearance_history h JOIN clearance c ON c.id=h.clearance_id
                                JOIN students s ON s.id=c.student_id JOIN offices o ON o.id=c.office_id
                                ORDER BY h.id DESC LIMIT ?""", (a.limit,)):
            print(f"{r['created_at']}  {r['name']:<16} {r['office']:<19} {r['old_status'] or '-':>8} -> {r['new_status']}  {r['note'] or ''}")


def main():
    p = argparse.ArgumentParser(description="ClearGate Student Clearance Portal")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    p.set_defaults(fn=cmd_serve)
    sub = p.add_subparsers()

    s = sub.add_parser("add-student", help="add a student")
    s.add_argument("--student-no", required=True)
    s.add_argument("--email", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--course", required=True, help='e.g. "2nd Year, BSIT"')
    s.add_argument("--year", default="A.Y 2026 - 2027")
    s.add_argument("--password")
    s.set_defaults(fn=cmd_add_student)

    s = sub.add_parser("set-status", help="update a student's clearance at one office")
    s.add_argument("--student", required=True, help="student number or email")
    s.add_argument("--office", required=True)
    s.add_argument("--status", required=True, choices=STATUSES)
    s.add_argument("--detail", help='short text, e.g. "1 unreturned book"')
    s.add_argument("--summary", help="text for the dashboard card (defaults to the detail)")
    s.add_argument("--note")
    s.set_defaults(fn=cmd_set_status)

    s = sub.add_parser("log", help="show gathered activity")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(fn=cmd_log)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
