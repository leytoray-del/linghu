from erf.seed import DEMO_PASSWORD


def test_requires_sign_in(anon) -> None:  # type: ignore[no-untyped-def]
    r = anon.get("/api/v1/requests")
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_login_sets_http_only_session_cookie(anon) -> None:  # type: ignore[no-untyped-def]
    r = anon.post("/api/v1/auth/login", json={"email": "ALEX.TAN@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Alex Tan"
    set_cookie = r.headers.get_list("set-cookie")
    assert any(c.startswith("erf_session=") and "HttpOnly" in c for c in set_cookie)
    assert any(c.startswith("erf_csrf=") and "HttpOnly" not in c for c in set_cookie)


def test_wrong_password_and_lockout(anon) -> None:  # type: ignore[no-untyped-def]
    for _ in range(5):
        r = anon.post("/api/v1/auth/login", json={"email": "alex.tan@example.com", "password": "wrong"})
        assert r.status_code == 401
    r = anon.post("/api/v1/auth/login", json={"email": "alex.tan@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 401
    assert "locked" in r.json()["message"]


def test_state_change_requires_csrf_header(login) -> None:  # type: ignore[no-untyped-def]
    s = login("alex.tan@example.com")
    del s.client.headers["X-CSRF-Token"]
    r = s.post("/requests", json={"project_name": "x"})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"


def test_logout_ends_session(login) -> None:  # type: ignore[no-untyped-def]
    s = login("alex.tan@example.com")
    assert s.post("/auth/logout").status_code == 200
    assert s.get("/auth/me").status_code == 401


def test_change_password(login) -> None:  # type: ignore[no-untyped-def]
    s = login("alex.tan@example.com")
    r = s.post("/auth/change-password", json={"current_password": DEMO_PASSWORD, "new_password": "short"})
    assert r.status_code == 422
    r = s.post(
        "/auth/change-password", json={"current_password": DEMO_PASSWORD, "new_password": "N3w-Password!"}
    )
    assert r.status_code == 200
    assert s.get("/auth/me").status_code == 200
    login("alex.tan@example.com", "N3w-Password!")


def test_admin_creates_user_with_temporary_password(login) -> None:  # type: ignore[no-untyped-def]
    admin = login("admin@example.com")
    r = admin.post(
        "/admin/users", json={"email": "new.pm@example.com", "display_name": "New PM", "roles": ["REQUESTER"]}
    )
    assert r.status_code == 201, r.text
    temp = r.json()["temporary_password"]
    new = login("new.pm@example.com", temp)
    assert new.me["must_change_password"] is True


def test_non_admin_cannot_use_admin_api(login) -> None:  # type: ignore[no-untyped-def]
    assert login("priya.nair@example.com").get("/admin/users").status_code == 403
