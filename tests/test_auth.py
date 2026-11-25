from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.db.types import utcnow
from app.models import RefreshTokenModel, UserModel
from tests.conftest import TEST_SECRET_KEY


def test_register_login_and_me(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "  Joao@Example.com  ", "password": "Password123", "full_name": "João"},
    )
    assert reg.status_code == 201
    user = reg.json()
    assert user["email"] == "joao@example.com"
    assert user["role"] == "user"
    assert user["is_active"] is True
    assert "hashed_password" not in user

    # E-mail duplicado -> 409
    dup = client.post(
        "/api/v1/auth/register",
        json={"email": "JOAO@example.com", "password": "Password123", "full_name": "Outro"},
    )
    assert dup.status_code == 409
    assert dup.json()["code"] == "conflict"

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "joao@example.com", "password": "Password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900

    # /me
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "joao@example.com"


@pytest.mark.parametrize(
    "password",
    ["short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"],
)
def test_register_rejects_weak_password(client, password):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": password, "full_name": "Teste"},
    )
    assert res.status_code == 422


def test_login_invalid_credentials(client, register_and_login):
    register_and_login("valid@example.com", "StrongPass123", "Válido")
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "valid@example.com", "password": "WrongPass123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "missing@example.com", "password": "StrongPass123"}
        ).status_code
        == 401
    )


def test_expired_and_malformed_access_tokens_rejected(client, register_and_login):
    register_and_login()
    now = utcnow()
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        TEST_SECRET_KEY,
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )

    wrong_type = jwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        TEST_SECRET_KEY,
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {wrong_type}"}).status_code
        == 401
    )

    bad_sub = jwt.encode(
        {
            "sub": "not-an-int",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        },
        TEST_SECRET_KEY,
        algorithm="HS256",
    )
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {bad_sub}"}).status_code
        == 401
    )


def test_refresh_token_rotation_and_reuse_detection(client, register_and_login):
    tokens1, _ = register_and_login()
    rt1 = tokens1["refresh_token"]

    # Rotação normal: rt1 -> rt2
    res2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert res2.status_code == 200
    rt2 = res2.json()["refresh_token"]
    assert rt2 != rt1

    # Reuso de rt1 (replay attack) -> 401 E revoga toda a família (incluindo rt2!)
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert replay.status_code == 401

    # rt2 agora também está revogado por segurança
    after_replay = client.post("/api/v1/auth/refresh", json={"refresh_token": rt2})
    assert after_replay.status_code == 401


def test_refresh_token_unknown_and_expired(client, register_and_login):
    tokens, _ = register_and_login()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40}).status_code == 401

    # Força expiração no banco
    db = client.app.state.session_factory()
    try:
        stored = db.query(RefreshTokenModel).first()
        assert stored is not None
        stored.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_logout_revokes_refresh_token(client, register_and_login):
    tokens, headers = register_and_login("bob@example.com", "StrongPass123", "Bob")
    rt = tokens["refresh_token"]

    out = client.post("/api/v1/auth/logout", json={"refresh_token": rt}, headers=headers)
    assert out.status_code == 204

    # Refresh após logout falha com 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt}).status_code == 401

    # Logout com refresh token de outro usuário falha com 401
    other_tokens, _ = register_and_login("carol@example.com", "StrongPass123", "Carol")
    cross = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": other_tokens["refresh_token"]},
        headers=headers,
    )
    assert cross.status_code == 401


def test_inactive_user_blocked_on_login_me_and_refresh(client, register_and_login):
    tokens, headers = register_and_login("inactive@example.com", "StrongPass123", "Inativo")

    db = client.app.state.session_factory()
    try:
        user = db.query(UserModel).filter_by(email="inactive@example.com").first()
        assert user is not None
        user.is_active = False
        db.commit()
    finally:
        db.close()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "inactive@example.com", "password": "StrongPass123"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
