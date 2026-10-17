# Cohortix Setup

One Django backend (port 8000) serves everything under `/api`:

- `accounts` app: registration, login, profile, JWT authentication
- `ai` app: Gemini question generation/evaluation and camera checks (YOLO11m people/phones, YuNet faces)

The React client (port 5173) talks to it.

## Prerequisites

- Python 3.11 or 3.12 (PyTorch/YOLO wheels)
- Node.js 18+
- MongoDB locally or a MongoDB Atlas cluster
- A Gemini API key (https://aistudio.google.com/apikey)

## Backend

Everything Python lives in `server/`, including its virtualenv (`server/.venv`).

```bash
cd server
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit the values
python manage.py migrate
python manage.py runserver 8000
```

Always run `manage.py` with the venv's Python (activate it, or call `.venv/bin/python`).

`server/.env` values:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django signing key (required when `DJANGO_DEBUG` is not `True`) |
| `JWT_SECRET` | Signs login tokens |
| `MONGODB_URI`, `MONGODB_NAME` | Database connection |
| `GEMINI_API_KEY` | AI features (Google AI Studio key) |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | Gemini models to use; fallbacks are tried when the main one is busy or retired |
| `CORS_ALLOWED_ORIGINS` | Allowed frontend origins |
| `FRONTEND_URL` | Sign-in link printed by `onboard_institution` |

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
Never commit `server/.env`.

## Onboard your first institution

There is no public sign-up; accounts start from an onboarded institution.

```bash
cd server && source .venv/bin/activate
python manage.py onboard_institution
```

It asks for the institution's details and its first admin, then prints the
sign-in details. The admin must replace the temporary password at first sign-in.
Use `--no-input` with flags for scripted onboarding (`--help` lists them).

The admin then adds educators, students and other admins from **People → Users**
(one at a time) or **People → Import users** (CSV). Students are placed in a cohort,
which can be created from the same form or during an import.

After signing in, each role lands on its own home: admins on the institution
dashboard, educators on their teaching workspace, students on their personal hub.

Educators schedule tests from **Tests → Create test** (questions come from the
question bank, so save some there first, e.g. with the AI generator). Students in
the chosen cohort find them under **My tests**.

Run `python manage.py migrate` after pulling: scheduled tests add the
`assessments` 0002 migration, proctoring adds `assessments` 0003-0004 and `ai` 0004.

Camera and phone checks need two model files in `server/models/` (YOLO11m, 40 MB, and the
YuNet face detector, 232 KB; downloaded and checksum-verified, not committed):

```bash
python manage.py fetch_proctoring_models
```

Without them those checks show as unavailable. To measure detection on your own labelled frames
(a JSON list of `{"file": "a.jpg", "people": 1, "phone": false}`, paths relative to the list):

```bash
python manage.py evaluate_proctoring labels.json
```

It prints per-frame precision, recall and false-positive rate for "no one", "more than one
person" and phones, plus latency. Thresholds are in `PROCTORING` in `config/settings.py` (README,
"Tuning").

## Branding: logo and colours (Django admin)

Platform staff set each institution's logo and theme colours in Django's admin at
`http://localhost:8000/admin/` (separate from the in-app admin portal). Create a staff login once:

```bash
python manage.py migrate          # includes the admin/auth tables (mongo_migrations/)
python manage.py createsuperuser
```

Then open **Institutions → <institution>**:

- **Logo**: PNG, JPG or WebP up to 2 MB (stored as a 256 px PNG), or **Remove the current logo**.
- **Primary / Secondary colour**: used by every admin, educator and student of that institution and
  on its sign-in page (`/login?school=<slug>`). Colours too light for white text are darkened
  automatically where text sits on them (WCAG AA, 4.5:1).
- **Use Cohortix's default colours**: back to the per-role colours (admins blue, educators green,
  students violet).

Users see changes the next time they load the app. In production, run
`python manage.py collectstatic` and serve `STATIC_ROOT` (the admin's CSS/JS) from your web server.

## Frontend

```bash
cd client
npm install
npm run dev
```

The client calls `http://localhost:8000/api` by default; override with `VITE_API_URL`.

## Run both

`./start-backends.sh` (macOS/Linux) or `start-backends.bat` (Windows) starts the Django server.

## API

- Auth: `POST /api/auth/login`, `GET /api/auth/logout`, `POST /api/auth/logout-all`,
  `GET /api/auth/me`, `PUT /api/auth/updatedetails`, `PUT /api/auth/updatepassword`
- Institution admin (JWT): `/api/institution/overview`, `/activity`, `/users` (+ `/import`,
  `/<id>/reset-password`), `/cohorts` (+ `/<id>`)
- Educators (JWT): `/api/teaching/overview`, `/api/teaching/students`, `/api/questions`,
  `/api/assessments` (+ `/<id>`) for scheduled tests
- Students (JWT): `/api/me/performance`, `/api/me/tests` (+ `/<id>`, `/<id>/start`,
  `/<id>/answers`, `/<id>/submit`)
- AI (JWT required, `POST`): `/api/ai/generate-question`, `/api/ai/evaluate-answer`,
  `/api/ai/generate-mcq-questions`, `/api/ai/evaluate-mcq-answers`,
  `/api/ai/analyse-frame` (interview camera checks), `/api/ai/detect-faces`,
  `/api/ai/detect-phone` (older single checks), `/api/ai/session`; `GET /api/ai/proctoring-config`
- `GET /api/health`

## Troubleshooting

- **Mongo connection timeout**: add your IP to the Atlas Network Access list.
- **AI calls fail with 502**: the server log shows Google's reason. "No longer available"
  means Google retired the model: set `GEMINI_MODEL` to a current one (see
  https://ai.google.dev/gemini-api/docs/models) and restart the server. A rejected key means
  `GEMINI_API_KEY` is wrong. `.env` is read at startup, so restart after editing it.
- **CORS errors**: add the frontend origin to `CORS_ALLOWED_ORIGINS`.
- **First camera check is slow** (about 1 s): the models load on first use.
- **Camera checks show as unavailable**: run `python manage.py fetch_proctoring_models`.
- **A test shows the wrong start time**: times are entered in the educator's browser time
  zone and shown in each viewer's own. Countdowns follow the server clock, so a wrong
  computer clock doesn't open or close a test early.
