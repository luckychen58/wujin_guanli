# Hardware Order Management System

A lightweight full-stack hardware order management system for wholesalers and trading teams.

## Stack

- Frontend: static HTML, CSS, and ES modules
- Backend: Python standard library HTTP server
- Database: SQLite
- Auth: cookie-based session auth with role permissions, menu visibility, and audit logging

## Active modules

- `server.py`: local server entry point
- `backend/db.py`: SQLite schema, initialization, and business-data reset helpers
- `backend/seed.py`: base customer and product seed data
- `backend/auth.py`: user accounts, password hashing, sessions, role permissions, menu access, and audit logging
- `backend/services.py`: order, inventory, purchase, and receivable domain logic
- `backend/server.py`: API routing, auth checks, admin endpoints, and static file serving
- `src/store.js`: browser state store
- `src/services.js`: frontend API client with session-aware error handling
- `src/render.js`: login, menu-driven dashboard, user management, and menu configuration rendering
- `src/main.js`: frontend bootstrap

## Run locally

1. Open a terminal in this folder.
2. Run `python server.py`.
3. Open `http://127.0.0.1:8000` in a browser.

## Default demo accounts

- `admin / admin123`: full access, audit visibility, user management, menu configuration, and demo reset
- `sales / sales123`: create orders and view assigned menus
- `warehouse / warehouse123`: ship orders and view assigned menus
- `procurement / purchase123`: receive purchase tasks and view assigned menus
- `finance / finance123`: collect payments and view assigned menus

## Core workflows

- Login and keep session with an HttpOnly cookie
- Create sales orders and reserve stock automatically
- Generate purchase tasks when shortages occur
- Receive purchase stock and re-allocate it to waiting orders
- Ship reserved stock
- Track receivables and register payments
- Manage users, reset passwords, and enable or disable accounts
- Configure menu visibility for each role
- Record login, business operations, and admin actions in the audit log

## Database

- SQLite file path: `data/hardware_oms.sqlite3`
- The server seeds reference data, demo users, and default role-menu mappings on first run.
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
- `POST /api/users`
- `POST /api/users/:id/update`
- `POST /api/users/:id/reset-password`
- `POST /api/roles/:role/menu-access`
- `POST /api/reset-demo` (admin only)

## Notes

- The existing `src/seed.js` file is legacy from the earlier single-page prototype and is no longer used by the app.
- Menu visibility and operation permissions are intentionally separate. Seeing a page does not grant action rights.
