def test_register_and_duplicate_email(client):
    body = {
        "name": "Alice",
        "email": "alice@example.com",
        "password": "password123",
    }

    created = client.post("/api/auth/register", json=body)
    duplicate = client.post("/api/auth/register", json=body)
    case_variant = client.post(
        "/api/auth/register",
        json={**body, "email": "ALICE@EXAMPLE.COM"},
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert case_variant.status_code == 409


def test_wrong_and_unknown_credentials_match(client, make_user):
    make_user()

    wrong_password = client.post(
        "/api/auth/login",
        data={"username": "alice@example.com", "password": "wrongpass"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        data={"username": "unknown@example.com", "password": "wrongpass"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_me_requires_authentication(client, make_user):
    headers, user = make_user()

    authenticated = client.get("/api/auth/me", headers=headers)
    unauthenticated = client.get("/api/auth/me")

    assert authenticated.status_code == 200
    assert authenticated.json()["email"] == user["email"]
    assert unauthenticated.status_code == 401
