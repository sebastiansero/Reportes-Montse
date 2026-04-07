from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ADMIN_USERNAME = "montse"
DEFAULT_ADMIN_PASSWORD = os.environ.get("REPORTES_ADMIN_PASSWORD", "montse2026")


class UserStore:
    def __init__(self, path: str = "config/users.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_store()

    def authenticate(self, username: str, password: str) -> dict | None:
        normalized = self._normalize_username(username)
        store = self._read_store()
        for user in store["users"]:
            if user["username"] != normalized or not user.get("active", True):
                continue
            if self._verify_password(password, user["password_hash"], user["password_salt"]):
                return self._public_user(user)
        return None

    def list_users(self) -> list[dict]:
        store = self._read_store()
        users = [self._public_user(user) for user in store["users"]]
        return sorted(users, key=lambda item: (not item["is_admin"], item["username"]))

    def create_user(self, username: str, password: str, *, created_by: str) -> dict:
        normalized = self._normalize_username(username)
        if not normalized:
            raise ValueError("El usuario es obligatorio.")
        if len(normalized) < 3:
            raise ValueError("El usuario debe tener al menos 3 caracteres.")
        if len(password) < 6:
            raise ValueError("La contrasena debe tener al menos 6 caracteres.")

        store = self._read_store()
        if any(user["username"] == normalized for user in store["users"]):
            raise ValueError("Ese usuario ya existe.")

        password_hash, password_salt = self._hash_password(password)
        now = datetime.now(timezone.utc).isoformat()
        user = {
            "username": normalized,
            "password_hash": password_hash,
            "password_salt": password_salt,
            "is_admin": False,
            "active": True,
            "created_at": now,
            "created_by": self._normalize_username(created_by),
        }
        store["users"].append(user)
        self._write_store(store)
        return self._public_user(user)

    def _ensure_store(self) -> None:
        store = self._read_store()
        if any(self._normalize_username(user.get("username")) == DEFAULT_ADMIN_USERNAME for user in store["users"]):
            return

        password_hash, password_salt = self._hash_password(DEFAULT_ADMIN_PASSWORD)
        admin_user = {
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": password_hash,
            "password_salt": password_salt,
            "is_admin": True,
            "active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
        }
        store["users"].insert(0, admin_user)
        self._write_store(store)

    def _read_store(self) -> dict:
        if not self.path.exists():
            return {"users": []}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if "users" not in data or not isinstance(data["users"], list):
            return {"users": []}
        return data

    def _write_store(self, data: dict) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=True)

    def _hash_password(self, password: str, salt: bytes | None = None) -> tuple[str, str]:
        salt = salt or os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
        return self._b64(digest), self._b64(salt)

    def _verify_password(self, password: str, expected_hash: str, encoded_salt: str) -> bool:
        salt = base64.b64decode(encoded_salt.encode("ascii"))
        digest, _ = self._hash_password(password, salt=salt)
        return hmac.compare_digest(digest, expected_hash)

    def _public_user(self, user: dict) -> dict:
        username = self._normalize_username(user.get("username", ""))
        return {
            "username": username,
            "is_admin": username == DEFAULT_ADMIN_USERNAME,
            "active": bool(user.get("active", True)),
            "created_at": user.get("created_at", ""),
            "created_by": user.get("created_by", ""),
        }

    def _normalize_username(self, username: str) -> str:
        return str(username or "").strip().lower()

    def _b64(self, value: bytes) -> str:
        return base64.b64encode(value).decode("ascii")
