# EduConnect — School & College Management Platform

EduConnect is a production-oriented, cloud-ready educational institution management system built with **Django 6**, the **official MongoDB Django Backend (`django-mongodb-backend`)**, **PyMongo**, and **Bootstrap 5**.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Language** | Python | 3.10 – 3.14+ | Core runtime |
| **Framework** | Django | 6.1.x | Web application framework |
| **Database Engine** | `django-mongodb-backend` | 6.1.x | Official MongoDB Inc. backend driver |
| **Driver / Pooling** | PyMongo (`pymongo[srv]`, `dnspython`) | 4.19+ | MongoDB client with SRV/Atlas support |
| **Database Target** | MongoDB Atlas / Local MongoDB | 6.0+ / 7.0+ / Atlas | Document datastore |
| **Primary Key Standard**| `ObjectIdAutoField` | MongoDB Native | Native BSON ObjectId generation |
| **Frontend UI** | Django Templates, Bootstrap 5.3, Icons | 5.3.3 | Responsive dark-mode dashboard |

---

## 📁 Directory Structure

```text
Education/
├── apps/                          # Modular Django application modules
│   └── core/                      # Core module: health checks, dashboard, diagnostics
│       ├── apps.py                # CoreConfig with ObjectIdAutoField
│       ├── context_processors.py  # Global template variables
│       ├── urls.py                # Core routes: /, /health/, /api/health/
│       └── views.py               # Health & diagnostics logic (safe from credential leakage)
├── educonnect/                    # Project package
│   ├── apps.py                    # MongoDB Admin, Auth, ContentTypes app configurations
│   ├── asgi.py                    # ASGI entrypoint
│   ├── wsgi.py                    # WSGI entrypoint
│   ├── urls.py                    # Root URL router
│   └── settings/                  # Separated environment settings
│       ├── __init__.py            # Dynamic environment selector (DJANGO_ENV)
│       ├── base.py                # Base configuration & MongoDB database wrapper
│       ├── development.py         # Local development settings (DEBUG=True)
│       └── production.py          # Production hardening (SSL, strict security headers)
├── media/                         # Uploaded files directory (avatars, documents)
├── mongo_migrations/              # MongoDB-compatible pre-packaged migrations
│   ├── admin/
│   ├── auth/
│   └── contenttypes/
├── static/                        # Static assets (CSS, JavaScript, Images)
│   ├── css/main.css               # Design system & dark mode styles
│   └── js/main.js                 # Frontend interactions & tooltips
├── templates/                     # HTML templates
│   ├── base.html                  # Base Bootstrap 5 layout
│   └── core/
│       ├── index.html             # Landing dashboard & platform highlights
│       └── health.html            # Visual system diagnostics interface
├── tests/                         # Automated test suite
│   ├── test_db_connection.py      # Real MongoDB connectivity & ping tests
│   └── test_healthcheck.py        # Health API and credential security tests
├── .env.example                   # Environment configuration template
├── .env                           # Active environment variables (git-ignored)
├── .gitignore                     # Git ignore rules
├── manage.py                      # Django management CLI
├── requirements.txt               # Pinned Python package dependencies
└── README.md                      # Project documentation
```

---

## ⚡ Prerequisites

1. **Python**: 3.10 or newer (tested on Python 3.14).
2. **MongoDB Database**:
   - **Option A (MongoDB Atlas - Cloud)**: Free M0 or dedicated Atlas cluster.
   - **Option B (Local MongoDB)**: MongoDB Community Server running locally on `localhost:27017`.

---

## 🚀 Quickstart Guide (Step-by-Step)

### Step 1: Create and Activate Virtual Environment

**Windows PowerShell:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux (Bash):**
```bash
python3 -m venv venv
source venv/bin/activate
```

---

### Step 2: Install Project Dependencies

Upgrade `pip` and install all required packages:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 3: Configure Environment Variables (`.env`)

Copy `.env.example` to create your active `.env` file:
```powershell
Copy-Item .env.example .env
```

Open `.env` in your editor and configure your database target:

#### For MongoDB Atlas (Cloud Cluster):
1. In the MongoDB Atlas console, navigate to **Database** → **Connect**.
2. Select **Drivers** (Python).
3. Copy the connection string and paste it into `.env`:
```env
DJANGO_ENV=development
DJANGO_SECRET_KEY=your-secure-random-secret-key-here
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver

MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority&appName=EduConnect
MONGODB_NAME=educonnect_prod
```
> **Note:** `dnspython` is already included in `requirements.txt` to support `mongodb+srv://` URI resolution.

#### For Local MongoDB:
```env
DJANGO_ENV=development
DJANGO_SECRET_KEY=django-insecure-educonnect-local-dev-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver

MONGODB_URI=mongodb://localhost:27017/
MONGODB_NAME=educonnect_db
```

---

### Step 4: Run System Checks & Apply Migrations

Run Django system check to verify settings and database router configuration:
```powershell
python manage.py check
```

Apply MongoDB migrations for authentication, sessions, and admin:
```powershell
python manage.py migrate
```

---

### Step 5: Execute Automated Verification Tests

Verify full MongoDB connectivity, ping latency, and credential protection:
```powershell
python manage.py test tests
```

Expected output:
```text
Creating test database for alias 'default'...
........
----------------------------------------------------------------------
Ran 8 tests in 0.48s

OK
Destroying test database for alias 'default'...
```

---

### Step 6: Seed Demonstration Content (Public Website)

Populate the database with realistic programs, campus facilities, achievements, notices, and gallery items:
```powershell
python manage.py seed_public_content
```

---

### Step 7: Create EduConnect Administrative User

Create a primary administrator user with the `Admin` role:
```powershell
python manage.py create_educonnect_admin --username admin --email admin@educonnect.local --password "YourStrongPassword123!" --first-name System --last-name Administrator
```
Or interactively create a superuser via Django standard CLI:
```powershell
python manage.py createsuperuser
```

---

### Step 8: Start the Development Server

Launch the local development server:
```powershell
python manage.py runserver
```

Open your browser and visit the public website and portals:
- **Public Website Pages:**
  - **Home (Landing Page):** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
  - **About EduConnect:** [http://127.0.0.1:8000/about/](http://127.0.0.1:8000/about/)
  - **Course Catalog:** [http://127.0.0.1:8000/courses/](http://127.0.0.1:8000/courses/)
  - **Institutional Achievements:** [http://127.0.0.1:8000/achievements/](http://127.0.0.1:8000/achievements/)
  - **Campus & Lab Gallery:** [http://127.0.0.1:8000/gallery/](http://127.0.0.1:8000/gallery/)
  - **Admissions & Inquiry Form:** [http://127.0.0.1:8000/admissions/](http://127.0.0.1:8000/admissions/)
  - **Contact Us & Inquiry Form:** [http://127.0.0.1:8000/contact/](http://127.0.0.1:8000/contact/)
  - **Visual Diagnostics:** [http://127.0.0.1:8000/health/](http://127.0.0.1:8000/health/)
  - **JSON Health API:** [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/)
- **Authentication & Role Portals:**
  - **Secure Sign In:** [http://127.0.0.1:8000/accounts/login/](http://127.0.0.1:8000/accounts/login/)
  - **Public Registration:** [http://127.0.0.1:8000/accounts/register/](http://127.0.0.1:8000/accounts/register/) (Applicants, Students, Parents, Teachers)
  - **User Profile:** [http://127.0.0.1:8000/accounts/profile/](http://127.0.0.1:8000/accounts/profile/)
  - **Role-Specific Dashboards:** `/accounts/dashboard/{admin,teacher,student,parent,accounts,applicant}/`
  - **Django Admin Portal:** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 👥 Role Architecture (6 Primary Roles)

EduConnect enforces strict server-side access control across six distinct user roles:

| Role | Access Level | Permitted Portals & Actions | Self-Registration Allowed? |
| :--- | :--- | :--- | :--- |
| **Admin** | Superuser / Institutional Head | Full control over users, courses, content, financials, system settings | ❌ Strictly Prohibited |
| **Accounts Staff** | Finance & Billing | Fee collections, receipts, student account balance management | ❌ Strictly Prohibited |
| **Subject Teacher** | Academic Staff | Course materials, syllabus, student rosters, grading, attendance | ✅ Yes (subject to admin approval) |
| **Student** | Active Learners | Enrolled courses, timetable, grade cards, fee payment tracking | ✅ Yes |
| **Parent** | Guardians | Linked child progress, attendance notifications, fee clearance | ✅ Yes |
| **Applicant** | Prospective Students | Application submissions, admission status tracking, inquiry history | ✅ Yes (Default Role) |

> **Role Isolation Guarantee:** Public registration form strictly limits role assignment. Any attempt to forge `admin` or `accounts` role during public registration raises an explicit HTTP 400 validation error.

---

## 🔒 Security Best Practices Implemented

1. **Zero Credential Leaks in Health Checks**: The `/api/health/` and `/health/` endpoints execute ping commands and read status while explicitly redacting all URIs, passwords, and sensitive connection parameters.
2. **Environment Variable Isolation**: Secret keys and connection strings live strictly in `.env`, which is permanently ignored by `.gitignore`.
3. **Dedicated Settings Modules**:
   - `educonnect.settings.development`: Enforces `DEBUG=True` with detailed debugging loggers.
   - `educonnect.settings.production`: Enforces `DEBUG=False`, SSL redirects, HTTP Strict Transport Security (HSTS), secure cookies (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`), and `X-Frame-Options: DENY`.
4. **Native MongoDB Compatibility**:
   - `DEFAULT_AUTO_FIELD = 'django_mongodb_backend.fields.ObjectIdAutoField'`
   - `DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]`
   - `MIGRATION_MODULES` redirected to official MongoDB-compatible migration packages.
5. **Session & Brute-Force Hardening**:
   - Session fixation protection upon successful authentication (`cycle_key()`).
   - Role-specific server-side permission checks via `@role_required` decorator with HTTP 403 `PermissionDenied` enforcement.
   - Sensitive view data protected against unauthorized role horizontal escalation.

