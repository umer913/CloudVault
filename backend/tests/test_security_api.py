from app.rate_limit import limiter


def test_security_headers_are_present(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )


def test_login_is_rate_limited(client):
    limiter.reset()
    try:
        responses = [
            client.post(
                "/api/auth/login",
                data={
                    "username": f"unknown-{index}@example.com",
                    "password": "wrong-password",
                },
            )
            for index in range(21)
        ]
    finally:
        limiter.reset()

    assert all(response.status_code == 401 for response in responses[:20])
    assert responses[20].status_code == 429
