from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import auth, db, services

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class HttpError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def log_message(self, format: str, *args) -> None:
        print("[http]" + format % args)

    def read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def send_json(self, status_code: int, payload: dict, cookies: list[str] | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for cookie in cookies or []:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def session_cookie(self, token: str, max_age: int) -> str:
        cookie = SimpleCookie()
        cookie[auth.SESSION_COOKIE_NAME] = token
        cookie[auth.SESSION_COOKIE_NAME]["path"] = "/"
        cookie[auth.SESSION_COOKIE_NAME]["httponly"] = True
        cookie[auth.SESSION_COOKIE_NAME]["max-age"] = str(max_age)
        cookie[auth.SESSION_COOKIE_NAME]["samesite"] = "Lax"
        return cookie[auth.SESSION_COOKIE_NAME].OutputString()

    def clear_session_cookie(self) -> str:
        cookie = SimpleCookie()
        cookie[auth.SESSION_COOKIE_NAME] = ""
        cookie[auth.SESSION_COOKIE_NAME]["path"] = "/"
        cookie[auth.SESSION_COOKIE_NAME]["httponly"] = True
        cookie[auth.SESSION_COOKIE_NAME]["max-age"] = "0"
        cookie[auth.SESSION_COOKIE_NAME]["samesite"] = "Lax"
        return cookie[auth.SESSION_COOKIE_NAME].OutputString()

    def get_session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(auth.SESSION_COOKIE_NAME)
        return morsel.value if morsel else None

    def get_actor(self, connection, permission: str | None = None):
        actor = auth.resolve_actor(connection, self.get_session_token())
        if not actor:
            raise HttpError(HTTPStatus.UNAUTHORIZED, "请先登录。")
        if permission:
            try:
                auth.require_permission(actor, permission)
            except auth.AuthorizationError as error:
                raise HttpError(HTTPStatus.FORBIDDEN, str(error)) from error
        return actor

    def build_payload(self, connection, actor):
        payload = {
            "viewModel": services.build_view_model(connection),
            "session": auth.session_payload(connection, actor),
            "auditLogs": [],
            "adminView": None,
        }
        if actor and auth.has_permission(actor["role"], "audit:view"):
            payload["auditLogs"] = auth.get_recent_audit_logs(connection)
        if actor and (
            auth.has_permission(actor["role"], "users:manage")
            or auth.has_permission(actor["role"], "menus:manage")
        ):
            payload["adminView"] = auth.build_admin_view(connection)
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/health":
                self.send_json(HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/api/view-model":
                with db.get_connection() as connection:
                    actor = self.get_actor(connection, "dashboard:view")
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                return

            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()
        except HttpError as error:
            self.send_json(error.status_code, {"error": error.message})
        except Exception as error:  # pragma: no cover - safety net for manual testing
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            with db.get_connection() as connection:
                if parsed.path == "/api/login":
                    payload = self.read_json()
                    username = str(payload.get("username") or "")
                    password = str(payload.get("password") or "")
                    with connection:
                        actor, token = auth.login(connection, username, password)
                    cookies = [self.session_cookie(token, auth.SESSION_MAX_AGE_SECONDS)]
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor), cookies=cookies)
                    return

                if parsed.path == "/api/logout":
                    token = self.get_session_token()
                    actor = auth.resolve_actor(connection, token)
                    with connection:
                        auth.logout(connection, token, actor)
                    self.send_json(
                        HTTPStatus.OK,
                        {"ok": True, "session": None, "auditLogs": []},
                        cookies=[self.clear_session_cookie()],
                    )
                    return

                if parsed.path == "/api/orders":
                    actor = self.get_actor(connection, "orders:create")
                    payload = self.read_json()
                    with connection:
                        order_id = services.create_order(connection, payload)
                        auth.write_audit_log(
                            connection,
                            action="orders.create",
                            entity_type="order",
                            entity_id=order_id,
                            actor=actor,
                            details={
                                "customerId": payload.get("customerId"),
                                "lineCount": len(payload.get("lines") or []),
                            },
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path == "/api/users":
                    actor = self.get_actor(connection, "users:manage")
                    payload = self.read_json()
                    with connection:
                        user = auth.create_user(connection, payload)
                        auth.write_audit_log(
                            connection,
                            action="users.create",
                            entity_type="user",
                            entity_id=user["id"],
                            actor=actor,
                            details={
                                "username": user["username"],
                                "role": user["role"],
                                "status": user["status"],
                            },
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/update") and parsed.path.startswith("/api/users/"):
                    actor = self.get_actor(connection, "users:manage")
                    user_id = parsed.path.split("/")[3]
                    payload = self.read_json()
                    with connection:
                        user = auth.update_user(connection, user_id, payload)
                        auth.write_audit_log(
                            connection,
                            action="users.update",
                            entity_type="user",
                            entity_id=user_id,
                            actor=actor,
                            details={
                                "displayName": user["displayName"],
                                "role": user["role"],
                                "status": user["status"],
                            },
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/reset-password") and parsed.path.startswith("/api/users/"):
                    actor = self.get_actor(connection, "users:manage")
                    user_id = parsed.path.split("/")[3]
                    payload = self.read_json()
                    password = str(payload.get("password") or "")
                    with connection:
                        auth.reset_user_password(connection, user_id, password)
                        auth.write_audit_log(
                            connection,
                            action="users.reset_password",
                            entity_type="user",
                            entity_id=user_id,
                            actor=actor,
                            details={},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/ship") and parsed.path.startswith("/api/orders/"):
                    actor = self.get_actor(connection, "orders:ship")
                    order_id = parsed.path.split("/")[3]
                    with connection:
                        services.ship_allocated_stock(connection, order_id)
                        auth.write_audit_log(
                            connection,
                            action="orders.ship",
                            entity_type="order",
                            entity_id=order_id,
                            actor=actor,
                            details={},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/payments") and parsed.path.startswith("/api/receivables/"):
                    actor = self.get_actor(connection, "receivables:collect")
                    receivable_id = parsed.path.split("/")[3]
                    payload = self.read_json()
                    amount = float(payload.get("amount") or 0)
                    with connection:
                        services.collect_payment(connection, receivable_id, amount)
                        auth.write_audit_log(
                            connection,
                            action="receivables.collect",
                            entity_type="receivable",
                            entity_id=receivable_id,
                            actor=actor,
                            details={"amount": amount},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/receive") and parsed.path.startswith("/api/purchases/"):
                    actor = self.get_actor(connection, "purchases:receive")
                    task_id = parsed.path.split("/")[3]
                    payload = self.read_json()
                    quantity = int(payload.get("quantity") or 0)
                    with connection:
                        services.receive_purchase(connection, task_id, quantity)
                        auth.write_audit_log(
                            connection,
                            action="purchases.receive",
                            entity_type="purchase_task",
                            entity_id=task_id,
                            actor=actor,
                            details={"quantity": quantity},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path.endswith("/menu-access") and parsed.path.startswith("/api/roles/"):
                    actor = self.get_actor(connection, "menus:manage")
                    role = parsed.path.split("/")[3]
                    payload = self.read_json()
                    menu_keys = payload.get("menuKeys") or []
                    with connection:
                        saved_menu_keys = auth.update_role_menu_access(connection, role, list(menu_keys))
                        auth.write_audit_log(
                            connection,
                            action="menus.update",
                            entity_type="role",
                            entity_id=role,
                            actor=actor,
                            details={"menuKeys": saved_menu_keys},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

                if parsed.path == "/api/reset-demo":
                    actor = self.get_actor(connection, "system:reset")
                    with connection:
                        db.reset_database(connection)
                        services.ensure_demo_data(connection)
                        auth.write_audit_log(
                            connection,
                            action="system.reset_demo",
                            entity_type="system",
                            entity_id="demo-data",
                            actor=actor,
                            details={},
                        )
                    self.send_json(HTTPStatus.OK, self.build_payload(connection, actor))
                    return

            self.send_json(HTTPStatus.NOT_FOUND, {"error": "未找到对应接口。"})
        except HttpError as error:
            self.send_json(error.status_code, {"error": error.message})
        except auth.AuthenticationError as error:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": str(error)})
        except auth.AuthorizationError as error:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": str(error)})
        except ValueError as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:  # pragma: no cover - safety net for manual testing
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})



def run_server(port: int) -> None:
    db.initialize_database()
    with db.get_connection() as connection:
        with connection:
            services.ensure_demo_data(connection)

    server = ThreadingHTTPServer(("127.0.0.1", port), AppHandler)
    print(f"Hardware OMS server running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()



def main() -> None:
    parser = argparse.ArgumentParser(description="Run the hardware OMS API server")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(args.port)


if __name__ == "__main__":
    main()
