# Drivas

A Django backend that connects **drivers** with **clients** entirely through **WhatsApp** (via Twilio).  
No mobile app, no web frontend — every user interaction happens in WhatsApp.

---

## Architecture

```
WhatsApp User
     │
     ▼
Twilio WhatsApp Business API
     │  POST /whatsapp/webhook/
     ▼
Django (this app)
  ├── messaging/  — webhook, conversation state machine, Twilio client
  ├── trips/      — Trip model + REST API (for operator tooling)
  ├── accounts/   — CustomUser, DriverProfile, ClientProfile
  └── Django Admin — operator manages users & monitors trips
     │
     ├── PostgreSQL  — persistent data
     ├── Redis       — Celery broker
     └── Celery      — async WhatsApp notifications
```

---

## WhatsApp Commands

### Client
| Command | Description |
|---------|-------------|
| `BOOK` | Start a new trip booking (multi-turn flow) |
| `STATUS <id>` | Check trip status |
| `CANCEL` | Cancel the current booking flow |
| `HELP` | Show the menu |

### Driver
| Command | Description |
|---------|-------------|
| `ACCEPT <id>` | Accept a pending trip |
| `START <id>` | Mark passenger picked up (trip in progress) |
| `DONE <id>` | Mark trip completed |
| `GOAVAIL` | Set status to Available |
| `GOOFFLINE` | Set status to Offline |
| `STATUS <id>` | Check trip status |
| `HELP` | Show the menu |

---

## Setup

### 1. Clone & install

```bash
git clone <repo>
cd rideconnect
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

### 3. Database

```bash
createdb rideconnect_db          # or use your DATABASE_URL
python manage.py migrate
python manage.py createsuperuser
```

### 4. Run services

```bash
# Terminal 1 — Django
python manage.py runserver

# Terminal 2 — Celery worker
celery -A rideconnect worker -l info

# Terminal 3 — expose localhost to Twilio (dev only)
ngrok http 8000
```

### 5. Configure Twilio webhook

In [Twilio Console](https://console.twilio.com) → Messaging → WhatsApp Sandbox (or your number):  
Set the **"When a message comes in"** webhook to:

```
https://<your-ngrok-url>/whatsapp/webhook/
```

Method: `HTTP POST`

---

## User Management

All users are created by operators via **Django Admin** (`/admin/`).

When creating a user:
1. Set `role` to `client` or `driver`
2. Set `whatsapp_number` in E.164 format (e.g. `+15551234567`)
3. For drivers: add a **DriverProfile** (vehicle info, license plate, mark `is_verified`)
4. Use the **"Send WhatsApp welcome message"** admin action to onboard the user

---

## REST API

An internal REST API is available for operator tooling at `/api/trips/`.  
Interactive docs: `/api/docs/`

---

## Production Checklist

- [ ] Set `DEBUG=False`
- [ ] Use a real PostgreSQL instance
- [ ] Use a production-grade Redis
- [ ] Run Celery with a process manager (e.g. systemd, Supervisor)
- [ ] Serve Django with Gunicorn behind Nginx
- [ ] Configure a real Twilio WhatsApp Business number (not sandbox)
- [ ] Set `ALLOWED_HOSTS` to your domain
- [ ] Rotate `SECRET_KEY`
