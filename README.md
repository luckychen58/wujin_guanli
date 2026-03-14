# Hardware Order Management System

A lightweight full-stack hardware order management system for wholesalers and trading teams.

## Stack

- Frontend: static HTML, CSS, and ES modules
- Backend: Python standard library HTTP server
- Database: SQLite
- Auth: cookie-based session auth with role permissions and audit logging

## Active modules

- `server.py`: local server entry point
- `backend/db.py`: SQLite schema, initialization, and business-data reset helpers
- `backend/seed.py`: base customer and product seed data
- `backend/auth.py`: user seed accounts, password hashing, sessions, roles, and audit logging
- `backend/services.py`: order, inventory, purchase, receivable domain logic
- `backend/server.py`: API routing, auth checks, and static file serving
- `src/store.js`: browser state store
- `src/services.js`: frontend API client with session-aware error handling
- `src/render.js`: login, dashboard, role-aware UI, and audit rendering
- `src/main.js`: frontend bootstrap

## Run locally

1. Open a terminal in this folder.
2. Run `python server.py`.
3. Open `http://127.0.0.1:8000` in a browser.

## Default demo accounts

- `admin / admin123`: full access, audit visibility, and demo reset
- `sales / sales123`: create orders
- `warehouse / warehouse123`: ship orders
- `procurement / purchase123`: receive purchase tasks
- `finance / finance123`: collect payments

## Core workflows

- Login and keep session with an HttpOnly cookie
- Create sales orders and reserve stock automatically
- Generate purchase tasks when shortages occur
- Receive purchase stock and re-allocate it to waiting orders
- Ship reserved stock
- Track receivables and register payments
- Record login and business operations in the audit log
- Reset demo business data while keeping system accounts

## Database

- SQLite file path: `data/hardware_oms.sqlite3`
- The server seeds reference data and demo users on first run.
- Demo business transactions are regenerated automatically.

## API endpoints

- `GET /api/health`
- `GET /api/view-model` (requires login)
- `POST /api/login`
- `POST /api/logout`
- `POST /api/orders`
- `POST /api/orders/:id/ship`
- `POST /api/purchases/:id/receive`
- `POST /api/receivables/:id/payments`
- `POST /api/reset-demo` (admin only)

## Notes

- The existing `src/seed.js` file is legacy from the earlier single-page prototype and is no longer used by the app.
- This is still a starter architecture. Next useful upgrades are CSRF protection, password change flows, finer-grained menu permissions, and a dedicated user-management screen.
