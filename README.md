# Cohortix

A multi-tenant assessment and AI interview platform for schools and colleges. Each institution gets its own isolated workspace of admins, educators and students, organised as Batch → Department → Section → Cohort, with a shared question bank (AI-generated, hand-written or imported from a sheet), scheduled and proctored tests, scored AI interviews, notes and messages with comments, and performance reports.

## 🚀 Features

### Authentication System

- **Institution branding**: each school or college uploads its logo; its name and logo lead the
  app ("Powered by Cohortix"), and `/login?school=<slug>` opens its branded sign-in page
- **Three role experiences, one design system**: admins get an institution command centre
  (blue), educators a teaching workspace (emerald), students a personal learning hub (violet)
- **Institution onboarding** by the platform operator (no public sign-up)
- **Roles**: admin, educator and student, each scoped to one institution
- **Temporary passwords** that must be replaced at first sign-in
- **JWT login** with bcrypt password hashing
- **Login throttling**: at most 5 password checks per email per 15 minutes
- **Form validation** with comprehensive error handling
- **Protected routes** with role-based access control
- **Bearer-token sessions**, revoked everywhere when a password changes

### Academic structure and people

- Students are organised in a four-level tree: **Batch → Department → Section → Cohort**
  (e.g. `2023-2027 → Computer Science → A → Lab group 1`). Names only need to be unique within
  their parent
- Every student sits in one cohort; tests and posts can be assigned to **any level**, and reach
  everyone below it
- Admins add people one at a time, or in bulk from a CSV: **add new users**, or **export** the
  current list, edit it in a spreadsheet and **update existing users** (matched by email, with
  every change shown before it's saved)

### Question bank

- Three ways to add multiple-choice questions under **Add Questions**: **generate with AI**
  (review and approve every draft), **write your own**, or **import from a sheet** (CSV from
  Excel or Google Sheets, with a sample file)
- Every question is reviewed by an educator before it's saved, and duplicates are flagged

### Scheduled tests

- Educators build **timed multiple-choice tests** from the question bank: title, who takes it
  (a whole batch, a department, a section or a single cohort), start time, duration, number
  of questions and marks per question
- Students see them under **My tests** (and on their home page) with a countdown; the test
  opens at its start time and closes for everyone when the duration ends
- One attempt per student, questions shuffled per student, answers **autosaved** as they go,
  resumable after a refresh, and **submitted automatically** when time runs out
- Graded on the server; correct answers and explanations are revealed only after the test closes
- Educators follow live results per student (submitted, in progress, not started, missed)

### Notes & messages

- Admins and educators share **messages** (announcements) and **notes** (study material with up to
  5 files: PDF, Office, images or text, 10 MB each) with a batch, department, section or cohort
- Every student under that group sees them under **Notes & Messages**, with a badge for new posts
  and the latest three on their home page
- Staff see how many students in the audience have opened each post; posts can be pinned, edited
  (by their author or an admin) and deleted
- Everyone who can see a post can **react** (👍 ❤️ 🎉 💡 🤔 🙏) and **comment**; staff comments are
  badged. People delete their own comments; a post's author and admins can delete any comment on it
  and turn comments off for a post

### Reports

- **Students** open **My Reports**: score trends for practice tests, AI interview answers and
  scheduled tests, weekly activity, averages by subject, every scheduled test against the average
  of everyone who took it, and comparisons with their cohort
- **Admins and educators** open **Reports** for the whole institution or any batch, department,
  section or cohort: score trends, weekly active students, the spread of students' scores, a
  breakdown one level down (click to drill in), subjects, recent tests, and a sortable student list
- Clicking any student (in Reports, My Students or a group page) opens **their** report
- Every chart has a date range (30 days to 12 months), a hover tooltip and a table view

### Proctoring in every test

- **Scheduled tests** are always proctored: full screen, camera checks, phone detection and
  microphone checks, each with its own limit; educators choose the checks and limits. Reaching a
  limit submits the test automatically, with the reason recorded
- **Practice tests** are proctored with the same default rules (no mark deductions, since practice
  is scored as a percentage), so students practise under real conditions
- **AI interviews** keep their live proctoring panel (people in frame, phone, tab switches), with the same camera evidence rules as tests
- Camera violations in scheduled tests deduct marks (5 by default); the final score never goes
  below zero. Every event is logged with time, confidence and action; educators review the
  timeline and can dismiss a flag (refunding its marks)

### Practice and AI features

- **AI-powered question generation** using Google's Gemini API
- **Real-time face detection** and monitoring
- **Cheating detection** (multiple faces, phone usage)
- **Answer evaluation** with AI scoring
- **Screenshot capture** for security
- **Responsive design** with modern UI

## 🛠️ Tech Stack

### Backend (Django)

- **Django 5.2** with the **django-mongodb-backend** (MongoDB / Atlas)
- **JWT** (PyJWT) for authentication, **bcrypt** for password hashing
- **django-cors-headers** for cross-origin requests
- `institutions` app: tenants, academic structure (Batch → Department → Section → Cohort), admin tools, branding, audit log
- `accounts` app: users, login, profile, login throttling
- `assessments` app: question bank, scheduled tests, sitting and grading
- `board` app: notes and messages shared with any group of students, with file attachments
- `reports` app: student and group performance reports (no models; reads practice and test results)
- `ai` app: Gemini question generation and evaluation, camera checks (YOLO11m, YuNet faces)

### Frontend (React.js)

- **React 19** with modern hooks
- **React Router** for navigation
- **React Hook Form** for form management
- **Axios** for API calls
- **Tailwind CSS v4** for styling. Design tokens live in `client/src/index.css`: the Plus
  Jakarta Sans type, radii, role-tinted shadows and a palette per role (admin blue → indigo,
  educator emerald → teal, student violet → fuchsia; signed-out screens indigo → violet).
  Shared components are in `client/src/components/ui.jsx`; `components/styles.js` has the
  button and input class recipes for links and bare inputs
- **React Hot Toast** for notifications
- **Heroicons** for icons

## 📋 Prerequisites

Before running this application, make sure you have the following installed:

- **Python** 3.11 or 3.12
- **Node.js** (v18 or higher) and npm
- **MongoDB** (local) or a free MongoDB Atlas cluster

## 🔧 Installation & Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd AI_Interview_System
```

### 2. Backend Setup (Django)

```bash
cd server
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # then fill in the values
python manage.py migrate
python manage.py runserver 8000
```

Key settings in `server/.env`: `MONGODB_URI`, `DJANGO_SECRET_KEY`, `JWT_SECRET`, `GEMINI_API_KEY`.
Never commit `server/.env`. The API runs on `http://localhost:8000/api`.

### 3. Frontend Setup (React)

Navigate to the client directory:

```bash
cd client
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will be running on `http://localhost:5173`

### 4. MongoDB Setup

Make sure MongoDB is running on your system:

**Windows:**

```bash
# Start MongoDB service
net start MongoDB
```

**macOS (with Homebrew):**

```bash
brew services start mongodb-community
```

**Linux:**

```bash
sudo systemctl start mongod
```

### 5. Upgrading an existing installation

After pulling, always run `python manage.py migrate` (from `server/`, with the virtualenv
active) and restart the API. Recent migrations:

| Migration | What it does to existing data |
| --- | --- |
| `institutions` 0006, `accounts` 0005, `assessments` 0005 | Adds Batch → Department → Section → Cohort. Existing cohorts move under a batch named after the academic year with a "General" department and section (rename them under **Structure**); students and tests keep their cohort |
| `board` 0001 | Notes & messages (new collections only) |
| `assessments` 0006 | Shared audience base for tests and posts (no data changes) |
| `board` 0002 | Comments and reactions; existing posts get comments switched on. Comments or reactions saved before migrating are kept |

[`SETUP.md`](SETUP.md) has the same notes plus more setup detail.

## 🔐 Security Features

### Password Security

- Passwords are hashed with bcrypt (cost 12)
- Minimum 6 characters with complexity requirements
- Password confirmation validation

### Authentication Security

- JWT Bearer tokens with expiration; changing or resetting a password revokes every other session
- No cookie authentication, so there is no CSRF surface; JSON endpoints require `Content-Type: application/json`
- At most 5 password checks per email per 15 minutes, identical for registered and unknown
  emails (no account enumeration); the same limit protects password changes

### Input Validation

- Server-side validation in Django views; client-side validation with react-hook-form
- CSV imports check every row before anything is saved; exported CSVs escape cells that
  spreadsheets would run as formulas (and imports undo that, so a round trip changes nothing)
- Uploaded files on posts: an allow-list of types (decided by extension, never by what the browser
  claims), 10 MB each, always served as downloads with `nosniff` and a sandboxing CSP
- CORS configuration

### API Security

- All AI endpoints require a valid JWT
- Stricter rate limiting for auth routes (5 requests per 15 minutes)
- Request timeout configuration
- Error handling without sensitive information exposure

## 📱 Usage

### 1. Onboard an institution

There is no public sign-up. The platform operator onboards each school or college
from the command line, which creates the institution and its first admin:

```bash
cd server && source .venv/bin/activate
python manage.py onboard_institution          # guided prompts
```

Or non-interactively (a temporary password is generated and printed once):

```bash
python manage.py onboard_institution --no-input \
  --name "Springfield College" --type college \
  --website springfield.edu --academic-year 2026-27 \
  --admin-name "Asha Rao" --admin-email asha@springfield.edu
```

Run `python manage.py onboard_institution --help` for every option. Send the admin
their sign-in details over a secure channel; they must choose a new password the
first time they sign in.

### 2. Set up the academic structure

Admins open **Structure** in the sidebar and build a tree of four levels:

**Batch** (e.g. `2023-2027`) → **Department** (`Computer Science`) → **Section** (`A`) → **Cohort** (`Lab group 1`)

Names only need to be unique within their parent, so every batch can have its own
`Computer Science` department. Each group can be renamed, and deleted once it has no
sub-groups, students or tests. Click a group for its stats and students.

### 3. Add users

Admins open **Administration → Users** in the sidebar and choose **Add user**:

- Pick a role: **Student**, **Educator** or **Admin**.
- Students are placed in a **batch, department, section and cohort** (all four are required).
  The move icon on a student's row changes their placement later.
- Set a password or **Generate** one. By default the person must choose their own
  password the first time they sign in.
- The confirmation screen shows the sign-in details to share (the password isn't shown again).

Many people at once: **Users → Import** asks what you want to do.

- **Add new users**: upload a CSV (`name,email,role,password,batch,department,section,cohort`).
  Blank passwords are generated and offered as a download.
- **Update existing users**: choose **Export** on the Users page (it exports what the current
  filters show; passwords are never exported), edit names, roles, placements or passwords, and
  upload the file. People are matched by email. The review lists every change ("Cohort: Lab 1 →
  Lab 2") before anything is saved. A blank password keeps theirs; a new password or a new role
  signs them out. You can't change your own role this way.

### 4. Login

- Navigate to `/login`
- Enter your email and password
- On first sign-in, replace the temporary password

### 5. Dashboard and settings

- Open **Settings** from your name at the bottom left of the sidebar. Tabs: **Profile** (name,
  email), **Account** (role, institution, sign out here or on all devices), **Password**, and for
  admins **Institution** (logo, name, academic year)
- Open your role's home: dashboard, teaching workspace or student hub

### 6. AI interview practice

- Navigate to `/interview`
- Use the camera system for face detection
- Generate AI questions by entering a subject
- Submit answers for AI evaluation

### 7. Adding questions

Educators and admins open **Add Questions**, which offers three ways to fill the question bank:

- **Generate with AI**: describe a subject (and topics), review every draft, edit or regenerate
  any of them, and save only the ones you approve
- **Write your own**: a question, four options, the correct answer and an optional explanation.
  Subject, topic and difficulty stay filled in after saving, so writing a set is quick
  (<kbd>Ctrl</kbd>+<kbd>Enter</kbd> saves)
- **Import from a sheet**: upload a CSV exported from Excel or Google Sheets (up to 500
  questions, 1 MB). Every row is checked first; rows with problems, or questions already in the
  bank, are skipped. Download the sample from the page, or use
  [`client/public/sample-questions.csv`](client/public/sample-questions.csv)

CSV columns: `subject, topic, difficulty, question, option_a, option_b, option_c, option_d,
correct_answer, explanation`. `topic`, `difficulty` (blank = medium) and `explanation` are
optional; `subject` is optional when you set a default subject on the page. `correct_answer` is
`A`-`D` or the exact text of the correct option. Short headers such as `Question, A, B, C, D,
Answer` work too.

### 8. Scheduled tests

Educators (and admins) open **Tests → Create test**:

- Enter a title, choose who takes it under **Assign to** (stop at any level: a batch,
  department, section or cohort; everyone below it gets the test), the **start time** (or **Start now**) and the **duration**.
- Set the **number of questions** and **marks per question**, then tick questions from the
  question bank (or **Pick N at random**). Short on questions? Add more under **Add Questions**.
- **Schedule test**. The test page shows each student's status and score as they submit.
  A test can be deleted until the first student starts it.

Students open **My tests**: live tests show **Start test**, upcoming ones a countdown. Answers
save automatically; use A–D to answer and ←/→ to move. Whatever is answered when time runs
out is submitted automatically.

### 9. Notes & messages

Admins and educators open **Notes & Messages** and choose **New post**: pick **Message** or
**Note**, choose who can see it (stop at any level: batch, department, section or cohort), write
it and attach files if you like. Untick **Allow comments** for an announcement that needs no replies.
Students find it under **Notes & Messages**; files download with their original names.

Under each post, students and staff can **react** (one click on 👍 ❤️ 🎉 💡 🤔 🙏) and **comment**.
Comments from educators and admins carry a role badge. Everyone can delete their own comments; the
post's author and admins can delete any comment on it.

### 10. Proctored tests

Every scheduled test is proctored. Educators choose which checks run and their limits in the
**Proctoring** card when creating a test (at least one check must stay on), and can change them
until the first student starts (**Edit rules** on the test page). Tests that students had already
started before proctoring was added keep running without it. Defaults:

| Check | What counts as one violation | Limit (auto-submit) | Penalty |
| --- | --- | --- | --- |
| Full screen | Leaving full screen, switching tab or app, or leaving/reloading the page | 3 | – |
| Microphone | About 2.5 s of speech within 4 s (sustained speech) | 5 | – |
| Camera | No one in view in 5 of the checks within 12 s, more than one person in 4 within 10 s, or the camera off for 30 s | 5 | 5 marks |
| Phone | A phone seen (≥35% confidence) in 3 of the checks within 10 s | 3 | – |

A limit of 0 means "warn only". One continuing problem counts once, and again every 60 s while it
lasts (it ends once the recent checks are clear); a full-screen exit and the tab hiding with it count as one switch (each exit after the
student returns to full screen counts again).

**Practice tests** follow these defaults too (camera checks only where the server can run them),
without mark deductions. Students see the rules, check their devices and enter full screen before
the first question; reaching a limit submits the practice test with the answers given so far, and
its result shows why. **Quit** ends a practice test without scoring it.

Students see the rules, allow the camera and microphone, then **Enter full screen and start**:
the test starts only once full screen succeeds. During the test the page covers the app (no
navigation) and a live **Proctoring** panel shows the camera, people in frame, phone, microphone,
full screen and the count per check; a warning appears after each violation. Leaving
full screen blocks the questions until the student returns. After a reload the test waits behind
a resume screen until devices and full screen are back.

**Scores.** `final = max(0, raw − penalties)`, where `raw` is marks from correct answers and
penalties are the camera-violation deductions recorded before submission. There are no partial
marks or negative marking. Educators adjust a result only by reviewing violations: open a
student's **Report**, then **Uphold** or **Dismiss** each event; dismissing refunds its penalty
and recomputes the final score. An automatic submission isn't undone by a dismissal.

**Authority.** The browser detects; the server decides. Each event carries an id that is unique
per attempt, so retries and duplicates never count twice; counters and penalties only change while
the attempt is open; the attempt is finalised exactly once (by the student, the timer or a limit,
whichever is first), and the reason is stored (`STUDENT_SUBMITTED`, `TIME_LIMIT`,
`SCREEN_SWITCH_LIMIT`, `VOICE_VIOLATION_LIMIT`, `FACE_VIOLATION_LIMIT`, `PHONE_DETECTION_LIMIT`).

**Privacy.** Nothing is recorded. Camera frames (one every 2 s, at most 640 px, JPEG) are
analysed in memory on the API server and discarded; only the resulting facts (people, faces,
phone boxes) go back to the browser, and only confirmed incidents are stored; audio is analysed only in the browser. Camera and
microphone are released when the test ends.

**Limitations.**
- Camera checks find people and faces; nobody is identified (a different person sitting the test
  isn't detected). They need the models in `server/models/` and `ultralytics`; without them,
  camera and phone checks are shown as unavailable and can't be turned on.
- Detection is not perfect (measured rates below): expect occasional missed phones, mainly small
  or partly hidden ones, and rare false incidents. Educators should review incidents before acting
  on them (**Uphold** / **Dismiss**).
- "Looking away" is a hint shown to the student only; it never counts as a violation.
- The microphone check detects sustained speech; it can't count distinct voices. Loud TV or music
  with speech may be flagged.
- Phones are only detected when the camera can see them.
- Browsers can't prevent a second device or another person out of view. Determined students can
  also tamper with their own browser; the server records how many camera checks ran
  ("Camera checks run" in the report) so missing proctoring is visible.
- Full screen needs a desktop browser: iPhone Safari doesn't support it for web pages.
- Camera checks run on the API server: about 85 ms of CPU per check on an Apple M-series laptop,
  one object-model inference at a time, so one process handles roughly 20 students at a check
  every 2 s. Large sittings need more workers, a GPU, a smaller model
  (`PROCTOR_OBJECT_MODEL=yolo11s.pt`, ~2x faster, lower phone recall), or a longer
  `PROCTOR_FRAME_INTERVAL_MS`.

#### How camera detection works

Per check (`server/ai/vision.py`, rules in `server/ai/detection.py`):

1. **Objects:** one YOLO11m pass at 640 px for people, phones and phone look-alikes (remote,
   mouse, keyboard, laptop, TV, book). A phone box overlapping a *more confident* look-alike box
   (IoU > 0.5) is dropped.
2. **Faces:** OpenCV's YuNet face detector (232 KB, ~4 ms) with eye/nose landmarks. Webcam framing
   (head and shoulders, often dim) is where person detection fails, so a confident face (≥0.8)
   counts as someone present even when no person box is found. Two people, or two confident faces,
   mean "more than one person".
3. **Head turn:** the nose's offset from the middle of the eyes gives "Looking away" (status only).
4. **Phone states:** below 25% *No phone detected*; 25-35% *Phone suspected* (shown, not evidence);
   ≥35% counts as evidence. Boxes are drawn on the student's preview.

In the browser (`createCameraEvidence` in `client/src/utils/proctoring.js`, shared by scheduled
tests, practice tests and AI interviews) each condition keeps a rolling window of recent checks:
an incident needs several matching checks in the window, so one blurry frame or a hand over the
face never counts, and one good frame in the middle of a real problem doesn't reset it. Old checks
age out; failed checks (network, model error) are not evidence either way and are reported
separately as *technical* events, as are camera disconnections. Each incident is reported once
(with an id, so the server records it once), then again only after the cooldown.

**Measured accuracy** (single frames, `python manage.py evaluate_proctoring`, labelled images
from COCO 2017 val: 200 phone / 200 hard negatives with laptops, remotes, keyboards, books and
mice; 329 webcam-style crops):

| | Before (YOLOv8n) | Now |
| --- | --- | --- |
| One person at the desk recognised as exactly one | 88.7% | 98.0% |
| Empty scene flagged as "no one" (recall / false-positive rate) | 98.7% / 2.2% | 98.0% / 1.7% |
| "More than one person" precision / recall | 68% / 97% | 100% / 93% |
| Phone recall / precision / false-positive rate | 32% / 94% / 2.0% | 61% / 93% / 4.5% |
| Phone recall for phones ≥0.5% of the frame (112 images) | 48% | 78% |
| Latency per check (Apple M-series CPU) | 19 ms | 85 ms |

These are per-frame rates on photos, not live webcams; an incident additionally needs repeated
evidence, which removes most single-frame errors but cannot fix a phone the model never sees. Small
sample for "more than one person" (29 images). Re-measure on your own labelled frames before
changing thresholds.

#### Tuning

All values live in `PROCTORING` in `server/config/settings.py`; each can be overridden with an
environment variable (restart after changing):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PROCTOR_OBJECT_MODEL` / `PROCTOR_FACE_MODEL` | `yolo11m.pt` / `face_detection_yunet_2023mar.onnx` | Model files in `server/models/` |
| `PROCTOR_INFERENCE_SIZE` | 640 | YOLO input size |
| `PROCTOR_PERSON_CONFIDENCE` | 0.5 | A person box counts |
| `PROCTOR_FACE_CONFIDENCE` / `PROCTOR_FACE_RESCUE_CONFIDENCE` | 0.6 / 0.8 | A face is visible / alone proves presence |
| `PROCTOR_PHONE_SUSPECT_CONFIDENCE` / `PROCTOR_PHONE_CONFIDENCE` | 0.25 / 0.35 | "Phone suspected" / counts as evidence |
| `PROCTOR_LOOKALIKE_IOU` | 0.5 | Overlap with a likelier look-alike that drops a phone box |
| `PROCTOR_LOOK_AWAY_YAW` | 0.6 | Head turn shown as "Looking away" |
| `PROCTOR_FRAME_INTERVAL_MS` | 2000 | Browser check interval |
| `PROCTOR_MIN_SERVER_INTERVAL_MS` | 1000 | Server refuses faster checks (per sitting) |
| `PROCTOR_ABSENCE_WINDOW_MS` / `PROCTOR_ABSENCE_FRAMES` | 12000 / 5 | Checks with no one needed in the window |
| `PROCTOR_MULTIPLE_WINDOW_MS` / `PROCTOR_MULTIPLE_FRAMES` | 10000 / 4 | Same for more than one person |
| `PROCTOR_PHONE_WINDOW_MS` / `PROCTOR_PHONE_FRAMES` | 10000 / 3 | Same for phones |
| `PROCTOR_CLEAR_RATIO` | 0.2 | An incident ends when at most this share of the window shows it |
| `PROCTOR_COOLDOWN_MS` | 60000 | A continuing incident counts again after this long |
| `PROCTOR_CAMERA_GRACE_MS` | 30000 | Camera off this long counts as a camera violation |

Raising a `*_FRAMES` value or lowering a confidence trades false alarms for misses; measure with
`evaluate_proctoring` (below) after any change. The browser receives the timing values with each
test's rules, so no frontend rebuild is needed.

## 🗂️ Project Structure

```
AI_Interview_System/
├── client/                    # React frontend
│   ├── public/
│   │   └── sample-questions.csv   # sample sheet for question imports
│   ├── src/
│   │   ├── components/        # shared UI (ui.jsx, charts.jsx, GroupPicker.jsx, board/, admin/ …)
│   │   ├── context/           # AuthContext
│   │   ├── hooks/             # useApi, useUnreadPosts, proctoring hooks …
│   │   ├── pages/             # admin/, educator/, student/, reports/, settings/, Board.jsx
│   │   └── utils/             # API client, structure tree, reports, board, CSV helpers (+ *.test.js)
│   └── package.json
├── server/                    # Django backend
│   ├── config/                # settings, URLs, JSON/CSV helpers
│   ├── institutions/          # tenants, Batch → Department → Section → Cohort, users admin,
│   │                          # CSV import/export, audit log, onboard_institution command
│   ├── accounts/              # users, roles, sign-in
│   ├── assessments/           # question bank (+ CSV import), scheduled tests, proctoring
│   ├── board/                 # notes & messages, attachments, comments, reactions
│   ├── reports/               # student and group performance reports
│   ├── ai/                    # Gemini questions and scoring, camera checks
│   └── manage.py
└── README.md
```

## 🔧 API Endpoints

### Authentication Routes

- `POST /api/auth/login` - User login
- `GET /api/auth/logout` - User logout
- `POST /api/auth/logout-all` - Sign out on every device (revokes all of the user's tokens)
- `GET /api/auth/me` - Get current user
- `PUT /api/auth/updatedetails` - Update user details
- `PUT /api/auth/updatepassword` - Update password

### Institution Admin Routes (JWT required)

- `GET /api/institution/overview` - Dashboard KPIs, 14-day practice activity, department performance (admin)
- `GET /api/institution/activity` - Audit log of administrative actions (admin)
- `GET /api/institution/users` - List users (admin); filters `role`, `batch`, `department`, `section`, `cohort`, `q`, `limit`, `offset`
- `POST /api/institution/users` - Add a user (admin): `name`, `email`, `role`, `password`, `cohortId` (students; batch, department and section follow from it), `requirePasswordChange`
- `PATCH /api/institution/users/<id>` - Move a student (admin): `cohortId`
- `POST /api/institution/users/import` - CSV import (admin), multipart `file` with columns `name,email,role,password,batch,department,section,cohort`; `mode=add` (default) creates people, `mode=update` changes existing ones matched by email (rows list their `changes`); `commit=false` validates every row, `commit=true` applies the valid ones; `createGroups=true` creates missing batches, departments, sections and cohorts
- `GET /api/institution/users/export` - The users as CSV in the import's columns (admin; never includes passwords); filters `role`, `batch`, `department`, `section`, `cohort`, `q`
- `POST /api/institution/users/<id>/reset-password` - New temporary password, signs the user out everywhere (admin)
- `GET /api/institution/structure` - The Batch → Department → Section → Cohort tree, each group with student, sign-in and practice stats (admin, educator)
- `POST /api/institution/structure` - Add a group (admin): `level` (`batch`, `department`, `section` or `cohort`), `name`, `parentId` (not for batches)
- `GET /api/institution/structure/<level>/<id>` - One group's stats and sub-groups; `PATCH` renames it (`name`), `DELETE` removes it once it has no sub-groups, students or tests (admin)

### Institution Profile and Branding

- `GET /api/institution` - The signed-in user's institution (any role); `PATCH` updates `name`, `academicYear`, `website` (admin)
- `POST /api/institution/logo` - Upload a logo (admin), multipart `logo`: PNG/JPG/WebP up to 2 MB, stored as a 256 px PNG; `DELETE` removes it
- `GET /api/institutions/<id>/logo` - The logo image (public, cacheable; linked from `institution.logoUrl`)
- `GET /api/institutions/by-slug/<slug>` - Public name and logo for the branded sign-in page

### Educator Routes (JWT required; educators and admins)

- `GET /api/teaching/overview` - Question-bank counts, section and subject performance
- `GET /api/teaching/students` - Students with practice stats; filters `batch`, `department`, `section`, `cohort`, `q`
- `GET /api/questions` - Question bank; filters `subject`, `difficulty`, `mine`, `q`
- `POST /api/questions` - Save reviewed questions (`{questions: [...]}`, up to 50)
- `DELETE /api/questions/<id>` - Delete a question (its author or an admin)
- `POST /api/questions/import` - CSV import of questions (educator, admin), multipart `file`; `commit=false` checks every row, `commit=true` saves the valid ones; optional `subject` fills blank subject cells

### Scheduled Test Routes (JWT required)

Educators see the tests they created; admins see every test in the institution.

- `GET /api/assessments` - Tests with submission counts and average score (educator, admin)
- `POST /api/assessments` - Schedule a test (educator, admin): `title`, `audience` (`{level, id}` of a batch, department, section or cohort), `startsAt`
  (ISO 8601 with a time zone), `durationMinutes` (5-300), `marksPerQuestion` (1-100),
  `numQuestions`, `questionIds` (from the question bank, 1-100), optional `instructions`,
  `subject`, `shuffleQuestions`. The questions are copied into the test, so later bank edits
  don't change it
- `GET /api/assessments/<id>` - Questions with answer keys, stats and every student's result;
  `DELETE` removes it until a student starts (its creator or an admin)
- `GET /api/me/tests` - The student's tests (assigned to their batch, department, section or cohort) with their attempt status
- `GET /api/me/tests/<id>` - One test as the student may see it now (no answer key until it closes)
- `POST /api/me/tests/<id>/start` - Start, or resume, the student's single attempt while it's open
- `PUT /api/me/tests/<id>/answers` - Autosave `{answers: {questionId: "A"-"D"}, review: [questionId]}`
- `POST /api/me/tests/<id>/submit` - Final submission (same body); accepted for 15 s after the
  close for network delay, after which the last autosave is graded

### Proctoring Routes (JWT required)

The API keeps the name `monitoring` for the rules object. Every scheduled test is proctored:
`enabled` may be omitted or `true`; `false` is refused.

- `GET /api/proctoring/capabilities` - Whether camera and phone checks can run here (educator, admin)
- `PATCH /api/assessments/<id>` - `{monitoring: {...}}`: change the rules until a student starts
  (keys: `enabled`, `fullscreenRequired`, `cameraRequired`, `microphoneRequired`, `phoneDetection`,
  `maxScreenSwitches`, `maxVoiceViolations`, `maxFaceViolations`, `facePenalty`, `maxPhoneViolations`;
  the same object on `POST /api/assessments`)
- `GET /api/assessments/<id>/violations?student=<id>` - Event timeline (the test's creator or an admin)
- `PATCH /api/assessments/<id>/violations/<eventId>` - `{reviewStatus: "upheld" | "dismissed"}` after submission
- `POST /api/me/tests/<id>/violations` - Student: `{eventId, type, detail, confidence, answers, review}`;
  types `screen_switch`, `voice`, `face`, `phone`, `technical`. Saves the answers, records the event
  once, applies penalties and submits at a limit; returns the updated test
- `POST /api/me/tests/<id>/frame` - Student: one webcam frame (multipart `image`), at most every
  `PROCTOR_MIN_SERVER_INTERVAL_MS`; returns `{people, peopleConfidence, faces, faceConfidence,
  lookingAway, phone, phoneSuspected, phoneConfidence, phoneBoxes, latencyMs}` (`phoneBoxes`:
  `[x1, y1, x2, y2, confidence]`, 0-1). Nothing is stored. The test's `monitoring.detection`
  holds the evidence rules the browser applies
- Practice tests (student, own quiz only): `GET /api/ai/practice/<quizId>` (rules, counts, and the
  result once submitted), `POST /api/ai/practice/<quizId>/violations` (same body as above with
  `answers`; reaching a limit grades those answers once and returns `{submitted: true, result}`),
  `POST /api/ai/practice/<quizId>/frame` (same as above). `generate-mcq-questions` returns the
  practice rules as `monitoring`

### Notes & Messages Routes (JWT required)

- `GET /api/board/posts` - Posts the caller can see (students: their groups'; staff: the institution's), pinned first then newest; filters `kind` (`message`/`note`), `q`, `limit`, `offset`, and for staff `batch`, `department`, `section`, `cohort`, `mine=true`. Students get `read`; staff get `canEdit`, `readers` and `audienceSize`
- `POST /api/board/posts` - Share a post (admin, educator), multipart: `kind`, `title`, `body`, `pinned`, `commentsEnabled`, `audienceLevel`, `audienceId`, up to 5 `files`
- `GET /api/board/posts/<id>` - One post; `PATCH` (`title`, `body`, `pinned`, `commentsEnabled`, `audience: {level, id}`) and `DELETE` for its author or an admin
- `GET /api/board/posts/<id>/comments` - The post's comments, oldest first (`offset`, `limit`); `POST` `{body}` adds one (anyone who can see the post, unless its comments are off)
- `DELETE /api/board/posts/<id>/comments/<commentId>` - Delete a comment (its author, the post's author, or an admin)
- `PUT /api/board/posts/<id>/reactions/<kind>` - React (`like`, `love`, `celebrate`, `insightful`, `curious`, `thanks`); `DELETE` removes it. Both return the post's `reactions`
- `POST /api/board/posts/<id>/read` - Student: mark as read
- `GET /api/board/unread` - Student: number of unread posts
- `POST /api/board/posts/<id>/attachments` - Add files (multipart `files`); `GET /api/board/posts/<id>/attachments/<fileId>` downloads one, `DELETE` removes it

### Reports Routes (JWT required)

All take `days` = `30`, `90` (default), `180` or `365`.

- `GET /api/reports/me` - Student: their own report (summary with cohort comparison, weekly `trend`, `subjects`, scheduled `tests` with the average of everyone who took each, `recent` practice)
- `GET /api/reports/students/<id>` - Admin, educator: the same report for one student
- `GET /api/reports/overview` - Admin, educator: the institution, or one group with `batch`, `department`, `section` or `cohort` (summary, weekly `trend` incl. active students, score `distribution`, `groups` one level down, `subjects`, recent `tests`, per-student `students`)

### Student Routes (JWT required)

- `GET /api/me/performance` - Overall and per-subject scores, streak, areas to improve, history

### AI Routes (JWT required, all `POST`)

- `/api/ai/generate-mcq-questions` - Any role. Students get a `quizId` and questions **without**
  answer keys; educators and admins get answer keys and explanations to review.
- `/api/ai/evaluate-mcq-answers` - Students: `{quizId, userAnswers}`, graded on the server, once.
- `/api/ai/generate-question`, `/api/ai/evaluate-answer` - Students: interview question by `questionId`, scored once.
- `/api/ai/detect-faces`, `/api/ai/detect-phone`, `/api/ai/session` - Students (proctoring).

### Health Check

- `GET /api/health` - Server health check

## 🚨 Important Security Notes

1. **Change JWT Secret**: Always change the `JWT_SECRET` in production
2. **Environment Variables**: Never commit `.env` files to version control
3. **HTTPS**: Use HTTPS in production so tokens and uploaded files are never sent in the clear
4. **Database Security**: Secure your MongoDB instance
5. **Rate Limiting**: Add throttling in front of the API (e.g. a reverse proxy) before going public
6. **CORS**: Configure CORS properly for your domain

## 🐛 Troubleshooting

### Common Issues

1. **MongoDB Connection Error**

   - Ensure MongoDB is running (or your Atlas IP allow-list includes you)
   - Check `MONGODB_URI` in `server/.env`

2. **CORS Errors**

   - Verify `CORS_ALLOWED_ORIGINS` in `server/.env`
   - Check if frontend URL is in allowed origins

3. **JWT Token Issues**

   - Clear browser cookies and localStorage
   - Check JWT_SECRET configuration

4. **Port Conflicts**
   - Run `runserver` on another port if 8000 is occupied
   - Set `VITE_API_URL` in the client accordingly

5. **A new feature half-works after pulling** (e.g. reactions work but comments are missing)
   - Run `python manage.py migrate` and restart the API. MongoDB creates collections on first
     use, so some features appear to work before their migration; the migrations are written to
     pick up such data rather than fail

6. **Backend tests seem to hang**
   - Make sure only one test command is running (see **Development → Tests**)
   - On a laptop, the machine may be sleeping: use `caffeinate -i` on macOS

## 📝 Development

### Adding New Features

1. Add views and URLs in the relevant Django app (`server/institutions`, `server/accounts`,
   `server/assessments`, `server/board`, `server/reports` or `server/ai`)
2. Add or change models, then run `makemigrations` and `migrate`
3. Update frontend components as needed
4. Test thoroughly before deployment

### Tests

- Backend: `cd server && .venv/bin/python manage.py test --noinput`. It creates (and then drops)
  a `test_` copy of the database named in `MONGODB_URI`, so point it at a local MongoDB rather
  than your Atlas cluster:

  ```bash
  MONGODB_URI="mongodb://localhost:27017/ai_interview_system" .venv/bin/python manage.py test --noinput
  ```

  The suite takes about 3 minutes. Run one test command at a time: parallel runs share the same
  `test_` database and break each other. On a Mac, prefix long runs with `caffeinate -i` so the
  machine doesn't sleep partway through.
- Frontend logic (proctoring rules, academic-structure tree, report helpers): `cd client && npm test`

### Code Style

- Use ESLint for code formatting
- Follow React best practices
- Implement proper error handling
- Add input validation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

If you encounter any issues or have questions, please:

1. Check the troubleshooting section
2. Review the code documentation
3. Create an issue in the repository

---

**Happy Coding! 🎉**
