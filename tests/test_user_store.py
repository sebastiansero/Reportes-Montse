from src.user_store import DEFAULT_ADMIN_USERNAME, UserStore


def test_user_store_seeds_admin_and_authenticates(tmp_path):
    store = UserStore(str(tmp_path / "users.json"))

    users = store.list_users()

    assert len(users) == 1
    assert users[0]["username"] == DEFAULT_ADMIN_USERNAME
    assert users[0]["is_admin"] is True
    assert store.authenticate(DEFAULT_ADMIN_USERNAME, "montse2026") is not None


def test_user_store_creates_regular_users(tmp_path):
    store = UserStore(str(tmp_path / "users.json"))

    user = store.create_user("equipo4", "secreto123", created_by="montse")

    assert user["username"] == "equipo4"
    assert user["is_admin"] is False
    assert store.authenticate("equipo4", "secreto123") is not None


def test_only_montse_is_admin_even_if_other_user_has_admin_flag(tmp_path):
    path = tmp_path / "users.json"
    path.write_text(
        """
{
  "users": [
    {
      "username": "equipo1",
      "password_hash": "x",
      "password_salt": "y",
      "is_admin": true,
      "active": true,
      "created_at": "",
      "created_by": "system"
    }
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    store = UserStore(str(path))
    users = store.list_users()

    assert any(user["username"] == DEFAULT_ADMIN_USERNAME and user["is_admin"] is True for user in users)
    assert any(user["username"] == "equipo1" and user["is_admin"] is False for user in users)
