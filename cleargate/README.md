# ClearGate - Student Clearance Portal

HTML/CSS front end built from your Figma screens, plus a brand-new SQLite database that
collects data as the portal is used. Needs only Python 3.9+ (no packages to install).

## Run it

```
python3 server.py
```

Open http://localhost:8000. The first run creates `cleargate.db` and one demo student:

| Student ID / email | Password |
|---|---|
| `2023-00123` or `ariel.tapnio@example.com` | `ClearGate#2026` |

Start with `CLEARGATE_SEED=0 python3 server.py` to skip the demo student.
Use `--port 9000` to change the port.

## Pages

| Screen | File |
|---|---|
| Login, Forgot password (3 steps), "You are all set" | `static/login.html` + `static/auth.js` |
| Dashboard, My Requirements, Clearance Status | `static/portal.html` + `static/portal.js` |
| All styling | `static/style.css` |
| Icons / logo | `static/icons.js`, `static/assets/cleargate-logo.png` |

**Logo:** `static/assets/cleargate-logo.png` is the supplied ClearGate logo.

## What the database gathers (`cleargate.db`)

| Table | New data it collects |
|---|---|
| `students` | Accounts (passwords stored as salted PBKDF2 hashes) |
| `offices` | The six offices |
| `clearance` | Each student's current status per office |
| `clearance_history` | Every status change: old -> new, when, and a note |
| `activity_log` | Logins, "View Details" opens, "Contact Office" clicks, password resets |
| `login_attempts` | Every sign-in try (also powers the 5-failures / 15-minute lockout) |
| `password_resets`, `sessions` | Reset codes (hashed) and signed-in sessions |

The dashboard re-reads the database every 30 seconds, so when an office updates a student the
change appears without a reload.

Students can also create an account from the login page. New accounts are saved in `students`
and start with all six office clearances pending. Student ID, email, name, course/year, academic
year, and a password of at least 8 characters are required.

## Adding data

```
python3 server.py add-student --student-no 2024-00456 --email maria@example.com \
    --name "Maria Santos" --course "2nd Year, BSIT"
python3 server.py set-status --student 2024-00456 --office Library --status action \
    --detail "2 unreturned books"
python3 server.py log          # see everything the database has gathered
```

Statuses: `approved`, `pending`, `action`. Offices: Registrar, Accounting, Library,
Guidance Office, Dean's Office, Property Custodian.

## Things to know

- **Password-reset emails are not sent.** No mail service is connected, so the 6-digit code is
  printed in the terminal running the server. To send real emails, put your SMTP / email-API
  call inside `send_reset_code()` in `server.py`.
- **Dashboard percentage:** it's calculated (4 of 6 = 67%). Your mockup shows 77%, which
  doesn't match 4 of 6.
- **No admin web page yet.** Offices update clearance through the CLI above; a staff-facing
  screen would be a separate piece of work.
- **Before real use:** run behind HTTPS and set `CLEARGATE_SECURE=1` (marks the session cookie
  Secure), and delete the demo student.
