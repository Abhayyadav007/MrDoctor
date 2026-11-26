# Patient Case Tracker

A local-first Django application for patient records, clinician workflows, appointments, secure case chat, and browser-to-browser calls. It uses PostgreSQL, Django Channels' in-memory layer, public STUN, and free/open-source packages. No paid APIs or paid hosting are required.

> **Privacy notice:** This is a development/demo application, not a certified medical-record system. Use synthetic data only. Do not expose real patient information through a public tunnel or deploy this configuration for clinical use.

## Requirements

- Python 3.11 or newer
- PostgreSQL 14 or newer
- A modern browser for video/audio calls
- Optional: `cloudflared` or `ngrok` only when testing from a second device

## Run with Docker Compose (recommended)

Docker Desktop is sufficient; Compose starts the app and PostgreSQL together without a paid service:

```bash
cp .env.example .env
```

Set a private random `SECRET_KEY` in `.env`, then start the application:

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000/>. Compose runs database migrations when the web container starts. In another terminal, create the single superadmin with a password entered interactively:

```bash
docker compose exec web python manage.py create_superadmin
```

The configured email defaults to `abhaykumar@example.test` and may be changed with `SUPERADMIN_EMAIL`. The command prompts for a strong password; no admin password is stored in the repository. Create the synthetic demo users, doctors, and cases with:

```bash
docker compose exec web python manage.py seed_demo
```

The demo admin is a regular admin account; the configured superadmin creates additional admins from the **Add admin** navigation link. Start/stop the containers with `docker compose up` and `docker compose down`; persisted database and uploaded files are held in named Docker volumes. To remove local database data as well, use `docker compose down -v`.

## Local Python setup

You can run Django directly on your computer while using your own PostgreSQL installation or Docker-managed PostgreSQL. For a local Homebrew PostgreSQL:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb patient_case_tracker
```

On Linux, install and start your distribution's PostgreSQL package, then create the database with `createdb patient_case_tracker`. Set the database user/password in `.env` to a local PostgreSQL role that can access this database (Homebrew installations commonly use your macOS account name as the role).

From the project directory:

```bash
python -m venv venv                  # use python3.11 -m venv venv if `python` is older than 3.11
source venv/bin/activate              # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env                  # Windows PowerShell: Copy-Item .env.example .env
```

Edit `.env`: set a random `SECRET_KEY`, set `DEBUG=True` for local development, add local names to `ALLOWED_HOSTS`, and set the PostgreSQL username/password for your installation. Then initialize the database and create an administrator:

```bash
python manage.py migrate
python manage.py createsuperuser
```

Alternatively, create a complete synthetic clinic:

```bash
python manage.py seed_demo
```

Demo credentials are `demo-admin / DemoAdmin123!`, `demo-doctor1` or `demo-doctor2 / DemoDoctor123!`, and `demo-patient1` through `demo-patient3 / DemoPatient123!`. Change these passwords before sharing the application.

Create the unique superadmin separately with `python manage.py create_superadmin`; this prompts for a password and uses the `SUPERADMIN_EMAIL` value in `.env`. Additional admin accounts can only be created by that superadmin from the **Add admin** page. Sign-in requires choosing the matching role (Patient, Doctor, or Admin).

Start the ASGI server (WebSockets are supported):

```bash
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Open <http://127.0.0.1:8000/>. Django's `python manage.py runserver` is also available for local development. Admin tools are at `/admin/`. Email sign-up requires verification; verification and password-reset links are printed to the terminal because the project uses Django's console email backend.

### Email and Google sign-in

Email/password sign-in, email verification, password reset, and account registration use django-allauth. Google sign-in/sign-up is enabled when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in `.env`. To configure it, create a free OAuth 2.0 Web application client in Google Cloud Console, add this authorized redirect URI, and copy its credentials to `.env`:

```text
http://127.0.0.1:8000/accounts/google/login/callback/
```

For another local host or HTTPS tunnel, add the matching callback URI to the OAuth client and use that hostname in `ALLOWED_HOSTS`. Google may require configuring the OAuth consent screen and adding test users while the consent screen is in testing mode. Do not commit OAuth secrets. Without Google credentials, email registration/sign-in still works and the Google button is hidden.

Admins should enter each doctor's real Google-account email when creating the doctor, and the superadmin should use the admin's real Google-account email when creating that admin. Google login matches a **verified** Google email to the existing account and keeps its assigned role; it does not grant admin or doctor access to a new Google signup. New Google signups continue to create patient accounts.

## Implementation and basic checks

1. **Setup and authentication:** email-based registration/login, email verification, password change/reset, optional Google sign-in/sign-up, custom roles, doctor account creation from the admin dashboard, and Django admin. Check email verification and reset flow; links appear in the server console.
2. **Records and scheduling:** create cases, assign doctors, upload attachments, record visits/prescriptions, request and decide appointments, browse patient history, audit case changes, and export a PDF. Use the seeded accounts to try patient and doctor workflows.
3. **Chat and calls:** open Messages for an assigned case. Chat history is persisted; the case WebSocket is restricted to that case's patient and assigned doctor. Start an audio or video call using the call buttons.
4. **Dashboards and polish:** role-specific dashboards, case/priority filtering, patient and case search/pagination, notifications, and admin charts are included.

Doctor ratings and administrator payroll tools are available from the dashboard/navigation. Patients can rate a doctor once per recovered or closed case. Admins set monthly base salary and rating bonus tiers, generate monthly drafts, record signed INR adjustments, approve drafts, and mark approved entries paid. Each administrative change is recorded in the payroll audit ledger.

### Manager and staff communication

Administrators can manage doctor-facing staff workflows: add dated remarks to a doctor's employee record, chat with doctors in real time, and schedule meetings with one or more doctors. Meetings support **Standard**, **Important**, and **Urgent** tags; employees see their remarks and meeting invitations under **My team**. The configured superadmin has the same manager tools and can additionally manage and message administrator accounts. Patients cannot access staff pages, messages, remarks, or meetings, and WebSocket chat connections enforce the same manager/employee relationship as the HTTP views.

Run the Django checks and full test suite with:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

GitHub Actions runs those checks and tests against PostgreSQL for pushes and pull requests, then verifies a Docker image build. It does not publish or deploy the image; no paid registry or hosting is configured.

## Video/audio testing

### Two browser sessions on one laptop

1. Run the server on `127.0.0.1:8000`.
2. Open one browser normally and sign in as a patient. Open a second browser or a private/incognito window and sign in as the doctor assigned to that patient's case.
3. Open the same case's chat in each session. Start a video or audio call in one window; accept it in the other.
4. Allow camera/microphone permissions. `localhost` and `127.0.0.1` are secure contexts, so device access is allowed without HTTPS.

Use separate accounts and separate browser profiles so each session has its own login cookie.

### Testing on two devices

Browsers require HTTPS for camera/microphone access on non-localhost origins. Keep the app on your computer and use a free HTTPS tunnel for temporary testing:

- **Cloudflare Quick Tunnel:** install the free `cloudflared` client, run the app locally, then run `cloudflared tunnel --url http://127.0.0.1:8000`. Open the generated `https://…trycloudflare.com` address from both devices.
- **ngrok free tier:** install the client, authenticate it with your own ngrok account token, then run `ngrok http 8000`. Open its HTTPS forwarding address on both devices.

For either tunnel, set `ALLOWED_HOSTS` in `.env` to include the generated hostname, add `https://<generated-host>/accounts/google/login/callback/` to the Google OAuth client if using Google sign-in, and restart the app. A tunnel makes the development server reachable from the internet; use synthetic accounts/data, and stop the tunnel when finished. Do not put an ngrok token or other credentials in this repository.

## WebSocket channel layer

Development uses `InMemoryChannelLayer`, so it needs no Redis installation and works with this single local server process. It is not shared across multiple server processes and is not suitable for production. To use Redis later, install a Redis server and `channels-redis`, then replace the `CHANNEL_LAYERS` setting in `config/settings.py` with:

```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [("127.0.0.1", 6379)]},
    },
}
```

Redis and `channels-redis` are optional; they are not in the default requirements.

## Limitations

- WebRTC uses Google's public STUN server only. Calls can fail on restrictive NATs or firewalls without a TURN relay.
- The in-memory channel layer is single-process and transient; it is intended only for local development.
- The app is an educational starter and has not undergone clinical, regulatory, or production security certification.

## Future improvements

- Add a configurable TURN server for broader WebRTC connectivity.
- Add durable Redis-backed channel layers and background jobs for multi-process deployment.
- Add stronger file validation/virus scanning, configurable retention, and encrypted object storage.
- Add richer audit events, MFA, organization-level administration, and automated accessibility checks.
- Add calendar integration, appointment reminders, and clinician availability scheduling.
