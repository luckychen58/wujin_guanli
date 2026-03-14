from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

SESSION_COOKIE_NAME = "hardware_oms_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 12
PBKDF2_ROUNDS = 120_000
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")

ROLE_LABELS = {
    "admin": "系统管理员",
    "sales": "销售",
    "warehouse": "仓库",
    "procurement": "采购",
    "finance": "财务",
}

ROLE_PERMISSIONS = {
    "admin": {
        "dashboard:view",
        "orders:create",
        "orders:ship",
        "purchases:receive",
        "receivables:collect",
        "audit:view",
        "system:reset",
        "users:manage",
        "menus:manage",
    },
    "sales": {"dashboard:view", "orders:create"},
    "warehouse": {"dashboard:view", "orders:ship"},
    "procurement": {"dashboard:view", "purchases:receive"},
    "finance": {"dashboard:view", "receivables:collect"},
}

MENU_DEFINITIONS = [
    {
        "key": "dashboard",
        "label": "经营概览",
        "description": "查看经营指标、客户概况和实时动作。",
    },
    {
        "key": "orders",
        "label": "订单中心",
        "description": "查看订单明细，并按角色执行录单或发货。",
    },
    {
        "key": "purchases",
        "label": "采购补货",
        "description": "查看欠货生成的采购补货任务并执行入库。",
    },
    {
        "key": "receivables",
        "label": "应收回款",
        "description": "查看应收台账并登记客户回款。",
    },
    {
        "key": "inventory",
        "label": "库存总览",
        "description": "查看库存、锁库和安全库存预警。",
    },
    {
        "key": "audit",
        "label": "操作审计",
        "description": "查看最近登录、业务动作和系统操作记录。",
    },
    {
        "key": "users",
        "label": "用户管理",
        "description": "新增账号、切换角色、启停用户和重置密码。",
    },
    {
        "key": "menu-config",
        "label": "菜单权限",
        "description": "配置各角色在前端可见的菜单范围。",
    },
]

DEFAULT_ROLE_MENUS = {
    "admin": {item["key"] for item in MENU_DEFINITIONS},
    "sales": {"dashboard", "orders", "inventory"},
    "warehouse": {"dashboard", "orders", "inventory"},
    "procurement": {"dashboard", "purchases", "inventory"},
    "finance": {"dashboard", "receivables"},
}

DEFAULT_USERS = [
    {
        "id": "USR-001",
        "username": "admin",
        "display_name": "系统管理员",
        "role": "admin",
        "password": "admin123",
    },
    {
        "id": "USR-002",
        "username": "sales",
        "display_name": "销售演示账号",
        "role": "sales",
        "password": "sales123",
    },
    {
        "id": "USR-003",
        "username": "warehouse",
        "display_name": "仓库演示账号",
        "role": "warehouse",
        "password": "warehouse123",
    },
    {
        "id": "USR-004",
        "username": "procurement",
        "display_name": "采购演示账号",
        "role": "procurement",
        "password": "purchase123",
    },
    {
        "id": "USR-005",
        "username": "finance",
        "display_name": "财务演示账号",
        "role": "finance",
        "password": "finance123",
    },
]


class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def validate_role(role: str) -> str:
    role = role.strip()
    if role not in ROLE_LABELS:
        raise ValueError("请选择有效角色。")
    return role


def validate_status(status: str) -> str:
    normalized = status.strip().upper()
    if normalized not in {"ACTIVE", "DISABLED"}:
        raise ValueError("账号状态必须是 ACTIVE 或 DISABLED。")
    return normalized


def ordered_menu_keys(menu_keys: set[str] | list[str]) -> list[str]:
    allowed = set(menu_keys)
    return [item["key"] for item in MENU_DEFINITIONS if item["key"] in allowed]


def get_menu_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in MENU_DEFINITIONS]


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = secrets.token_bytes(16) if salt_hex is None else bytes.fromhex(salt_hex)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ROUNDS,
    )
    return salt.hex(), password_hash.hex()


def verify_password(password: str, salt_hex: str, expected_hash_hex: str) -> bool:
    _, actual_hash = hash_password(password, salt_hex)
    return secrets.compare_digest(actual_hash, expected_hash_hex)


def get_permissions(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def serialize_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"],
        "role": row["role"],
        "roleLabel": role_label(row["role"]),
    }


def ensure_role_menu_access(connection: sqlite3.Connection) -> None:
    now = utc_now_iso()
    for role in ROLE_LABELS:
        default_keys = DEFAULT_ROLE_MENUS.get(role, set())
        for item in MENU_DEFINITIONS:
            connection.execute(
                """
                INSERT OR IGNORE INTO role_menu_access(role, menu_key, allowed, updated_at)
                VALUES(?, ?, ?, ?)
                """,
                (role, item["key"], 1 if item["key"] in default_keys else 0, now),
            )


def get_menu_keys(connection: sqlite3.Connection, role: str) -> list[str]:
    ensure_role_menu_access(connection)
    rows = connection.execute(
        """
        SELECT menu_key
        FROM role_menu_access
        WHERE role = ? AND allowed = 1
        ORDER BY menu_key ASC
        """,
        (role,),
    ).fetchall()
    return ordered_menu_keys([row["menu_key"] for row in rows])


def session_payload(connection: sqlite3.Connection, actor: dict[str, Any] | None) -> dict[str, Any] | None:
    if not actor:
        return None
    return {
        "currentUser": actor,
        "permissions": get_permissions(actor["role"]),
        "menus": get_menu_keys(connection, actor["role"]),
    }


def purge_expired_sessions(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM user_sessions WHERE expires_at <= ?",
        (utc_now_iso(),),
    )


def write_audit_log(
    connection: sqlite3.Connection,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
    username: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_logs(
            happened_at, user_id, username, display_name, role, action, entity_type, entity_id, details_json
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now_iso(),
            actor["id"] if actor else None,
            actor["username"] if actor else username,
            actor["displayName"] if actor else None,
            actor["role"] if actor else None,
            action,
            entity_type,
            entity_id,
            json.dumps(details or {}, ensure_ascii=False),
        ),
    )


def get_recent_audit_logs(connection: sqlite3.Connection, limit: int = 12) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM audit_logs ORDER BY happened_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "happenedAt": row["happened_at"],
            "username": row["username"] or "匿名",
            "displayName": row["display_name"] or row["username"] or "匿名",
            "role": row["role"] or "unknown",
            "roleLabel": role_label(row["role"]) if row["role"] else "未登录",
            "action": row["action"],
            "entityType": row["entity_type"],
            "entityId": row["entity_id"],
            "details": json.loads(row["details_json"] or "{}"),
        }
        for row in rows
    ]


def ensure_seed_users(connection: sqlite3.Connection) -> None:
    for item in DEFAULT_USERS:
        salt_hex, password_hash = hash_password(item["password"])
        connection.execute(
            """
            INSERT OR IGNORE INTO users(
                id, username, display_name, role, password_salt, password_hash, status, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'ACTIVE', ?)
            """,
            (
                item["id"],
                item["username"],
                item["display_name"],
                item["role"],
                salt_hex,
                password_hash,
                utc_now_iso(),
            ),
        )


def get_user_by_username(connection: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def get_user_by_id(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def create_session(connection: sqlite3.Connection, user_id: str) -> str:
    purge_expired_sessions(connection)
    token = secrets.token_urlsafe(32)
    now = utc_now()
    connection.execute(
        """
        INSERT INTO user_sessions(token, user_id, created_at, expires_at, last_seen_at)
        VALUES(?, ?, ?, ?, ?)
        """,
        (
            token,
            user_id,
            now.isoformat(),
            (now + timedelta(seconds=SESSION_MAX_AGE_SECONDS)).isoformat(),
            now.isoformat(),
        ),
    )
    return token


def destroy_session(connection: sqlite3.Connection, token: str | None) -> None:
    if not token:
        return
    connection.execute("DELETE FROM user_sessions WHERE token = ?", (token,))


def destroy_sessions_for_user(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))


def resolve_actor(connection: sqlite3.Connection, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    purge_expired_sessions(connection)
    row = connection.execute(
        """
        SELECT users.id, users.username, users.display_name, users.role, users.status, user_sessions.expires_at
        FROM user_sessions
        INNER JOIN users ON users.id = user_sessions.user_id
        WHERE user_sessions.token = ?
        """,
        (token,),
    ).fetchone()
    if not row:
        return None
    if row["status"] != "ACTIVE":
        destroy_session(connection, token)
        return None
    if datetime.fromisoformat(row["expires_at"]) <= utc_now():
        destroy_session(connection, token)
        return None
    connection.execute(
        "UPDATE user_sessions SET last_seen_at = ? WHERE token = ?",
        (utc_now_iso(), token),
    )
    return serialize_user(row)


def login(connection: sqlite3.Connection, username: str, password: str) -> tuple[dict[str, Any], str]:
    username = username.strip().lower()
    user = get_user_by_username(connection, username)
    if not user or not verify_password(password, user["password_salt"], user["password_hash"]):
        write_audit_log(
            connection,
            action="auth.login_failed",
            entity_type="session",
            entity_id=username or "unknown",
            username=username or "unknown",
            details={"reason": "invalid_credentials"},
        )
        raise AuthenticationError("用户名或密码错误。")
    if user["status"] != "ACTIVE":
        raise AuthenticationError("当前账号已停用。")
    actor = serialize_user(user)
    token = create_session(connection, user["id"])
    write_audit_log(
        connection,
        action="auth.login",
        entity_type="session",
        entity_id=user["id"],
        actor=actor,
        details={"username": actor["username"]},
    )
    return actor, token


def logout(connection: sqlite3.Connection, token: str | None, actor: dict[str, Any] | None) -> None:
    if actor:
        write_audit_log(
            connection,
            action="auth.logout",
            entity_type="session",
            entity_id=actor["id"],
            actor=actor,
            details={},
        )
    destroy_session(connection, token)


def require_permission(actor: dict[str, Any] | None, permission: str) -> dict[str, Any]:
    if not actor:
        raise AuthenticationError("请先登录。")
    if not has_permission(actor["role"], permission):
        raise AuthorizationError("当前角色没有此操作权限。")
    return actor


def next_user_id(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT id FROM users WHERE id LIKE 'USR-%' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return "USR-001"
    match = re.search(r"(\d+)$", row["id"])
    if not match:
        return "USR-001"
    return f"USR-{int(match.group(1)) + 1:03d}"


def validate_password(password: str) -> str:
    normalized = password.strip()
    if len(normalized) < 6:
        raise ValueError("密码至少需要 6 位。")
    return normalized


def serialize_user_profile(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    profile = serialize_user(row)
    profile["status"] = row["status"]
    profile["createdAt"] = row["created_at"]
    profile["lastSeenAt"] = row["last_seen_at"]
    profile["activeSessionCount"] = int(row["active_session_count"] or 0)
    profile["permissions"] = get_permissions(row["role"])
    profile["menus"] = get_menu_keys(connection, row["role"])
    return profile


def get_user_profile(connection: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT users.*, MAX(user_sessions.last_seen_at) AS last_seen_at, COUNT(user_sessions.token) AS active_session_count
        FROM users
        LEFT JOIN user_sessions
            ON user_sessions.user_id = users.id
            AND user_sessions.expires_at > ?
        WHERE users.id = ?
        GROUP BY users.id
        """,
        (utc_now_iso(), user_id),
    ).fetchone()
    if not row:
        return None
    return serialize_user_profile(connection, row)


def list_users(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT users.*, MAX(user_sessions.last_seen_at) AS last_seen_at, COUNT(user_sessions.token) AS active_session_count
        FROM users
        LEFT JOIN user_sessions
            ON user_sessions.user_id = users.id
            AND user_sessions.expires_at > ?
        GROUP BY users.id
        ORDER BY CASE users.role WHEN 'admin' THEN 0 ELSE 1 END, users.created_at ASC, users.id ASC
        """,
        (utc_now_iso(),),
    ).fetchall()
    return [serialize_user_profile(connection, row) for row in rows]


def create_user(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    username = str(payload.get("username") or "").strip().lower()
    display_name = str(payload.get("displayName") or "").strip()
    role = validate_role(str(payload.get("role") or ""))
    status = validate_status(str(payload.get("status") or "ACTIVE"))
    password = validate_password(str(payload.get("password") or ""))

    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("用户名需为 3-32 位字母、数字、点、下划线或中划线。")
    if not display_name:
        raise ValueError("请填写显示名称。")
    if get_user_by_username(connection, username):
        raise ValueError("用户名已存在，请更换。")

    salt_hex, password_hash = hash_password(password)
    user_id = next_user_id(connection)
    connection.execute(
        """
        INSERT INTO users(
            id, username, display_name, role, password_salt, password_hash, status, created_at
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            display_name,
            role,
            salt_hex,
            password_hash,
            status,
            utc_now_iso(),
        ),
    )
    return get_user_profile(connection, user_id)


def update_user(connection: sqlite3.Connection, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    user = get_user_by_id(connection, user_id)
    if not user:
        raise ValueError("未找到对应用户。")

    display_name = str(payload.get("displayName") or user["display_name"]).strip()
    role = validate_role(str(payload.get("role") or user["role"]))
    status = validate_status(str(payload.get("status") or user["status"]))

    if not display_name:
        raise ValueError("显示名称不能为空。")
    if user["username"] == "admin" and role != "admin":
        raise ValueError("默认管理员账号角色不可修改。")
    if user["username"] == "admin" and status != "ACTIVE":
        raise ValueError("默认管理员账号不能停用。")

    connection.execute(
        "UPDATE users SET display_name = ?, role = ?, status = ? WHERE id = ?",
        (display_name, role, status, user_id),
    )
    if status != "ACTIVE":
        destroy_sessions_for_user(connection, user_id)
    return get_user_profile(connection, user_id)


def reset_user_password(connection: sqlite3.Connection, user_id: str, new_password: str) -> dict[str, Any]:
    user = get_user_by_id(connection, user_id)
    if not user:
        raise ValueError("未找到对应用户。")

    password = validate_password(new_password)
    salt_hex, password_hash = hash_password(password)
    connection.execute(
        "UPDATE users SET password_salt = ?, password_hash = ? WHERE id = ?",
        (salt_hex, password_hash, user_id),
    )
    destroy_sessions_for_user(connection, user_id)
    return get_user_profile(connection, user_id)


def get_role_menu_matrix(connection: sqlite3.Connection) -> dict[str, list[str]]:
    ensure_role_menu_access(connection)
    rows = connection.execute(
        "SELECT role, menu_key, allowed FROM role_menu_access ORDER BY role ASC, menu_key ASC"
    ).fetchall()
    matrix = {role: [] for role in ROLE_LABELS}
    raw_sets = {role: set() for role in ROLE_LABELS}
    for row in rows:
        if int(row["allowed"]) == 1:
            raw_sets[row["role"]].add(row["menu_key"])
    for role, menu_keys in raw_sets.items():
        matrix[role] = ordered_menu_keys(menu_keys)
    return matrix


def update_role_menu_access(
    connection: sqlite3.Connection,
    role: str,
    menu_keys: list[str],
) -> list[str]:
    role = validate_role(role)
    allowed_keys = set(menu_keys)
    catalog_keys = {item["key"] for item in MENU_DEFINITIONS}
    unknown_keys = allowed_keys - catalog_keys
    if unknown_keys:
        raise ValueError("菜单配置里存在未知项。")

    now = utc_now_iso()
    for item in MENU_DEFINITIONS:
        connection.execute(
            """
            INSERT INTO role_menu_access(role, menu_key, allowed, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(role, menu_key) DO UPDATE SET
                allowed = excluded.allowed,
                updated_at = excluded.updated_at
            """,
            (role, item["key"], 1 if item["key"] in allowed_keys else 0, now),
        )
    return get_menu_keys(connection, role)


def build_admin_view(connection: sqlite3.Connection) -> dict[str, Any]:
    users = list_users(connection)
    role_counts = {role: 0 for role in ROLE_LABELS}
    for user in users:
        role_counts[user["role"]] += 1

    return {
        "users": users,
        "accessControl": {
            "roles": [
                {
                    "key": role,
                    "label": role_label(role),
                    "userCount": role_counts[role],
                }
                for role in ROLE_LABELS
            ],
            "menuCatalog": get_menu_catalog(),
            "roleMenus": get_role_menu_matrix(connection),
        },
    }
