import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pytest
from httpx import AsyncClient, ASGITransport
import main
from auth import init_auth_db, register_user, login_user

@pytest.fixture(autouse=True)
def setup_test_auth_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_auth.db")
    init_auth_db(test_db)
    monkeypatch.setattr("auth.AUTH_DB_PATH", test_db)
    yield test_db


@pytest.mark.asyncio
async def test_auth_profile_flow(setup_test_auth_db):
    db_path = setup_test_auth_db
    transport = ASGITransport(app=main.app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        reg_resp = await client.post("/api/register", json={
            "username": "ocean_tester",
            "email": "tester@ocean.org",
            "password": "StrongPassword123!"
        })
        assert reg_resp.status_code == 200
        assert reg_resp.json()["ok"] is True

        # 2. Login
        login_resp = await client.post("/api/login", json={
            "email": "tester@ocean.org",
            "password": "StrongPassword123!"
        })
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert data["ok"] is True
        token = data["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Get profile (/api/me)
        me_resp = await client.get("/api/me", headers=headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()["user"]
        assert me_data["username"] == "ocean_tester"
        assert me_data["email"] == "tester@ocean.org"
        assert "created_at" in me_data
        assert "conversation_count" in me_data

        # 4. Update username
        up_resp = await client.put("/api/profile/username", json={"username": "deep_diver_99"}, headers=headers)
        assert up_resp.status_code == 200
        assert up_resp.json()["username"] == "deep_diver_99"

        # Check /api/me reflects new username
        me_resp2 = await client.get("/api/me", headers=headers)
        assert me_resp2.json()["user"]["username"] == "deep_diver_99"

        # 5. Change password
        ch_resp = await client.post("/api/profile/password", json={
            "old_password": "StrongPassword123!",
            "new_password": "NewBetterPassword456!"
        }, headers=headers)
        assert ch_resp.status_code == 200
        assert ch_resp.json()["ok"] is True

        # 6. Verify login with new password
        login2 = await client.post("/api/login", json={
            "email": "tester@ocean.org",
            "password": "NewBetterPassword456!"
        })
        assert login2.status_code == 200
        assert login2.json()["ok"] is True

        # 7. Logout all
        lo_resp = await client.post("/api/profile/logout-all", headers=headers)
        assert lo_resp.status_code == 200
        assert lo_resp.json()["ok"] is True

        # After logout-all, old token is invalid
        me_invalid = await client.get("/api/me", headers=headers)
        assert me_invalid.status_code == 401

        # 8. Forgot Password Flow
        forgot_resp = await client.post("/api/forgot-password", json={"email": "tester@ocean.org"})
        assert forgot_resp.status_code == 200
        forgot_data = forgot_resp.json()
        assert forgot_data["ok"] is True
        assert "reset_code" in forgot_data
        code = forgot_data["reset_code"]

        # 9. Reset Password with Code
        reset_resp = await client.post("/api/reset-password", json={
            "email": "tester@ocean.org",
            "reset_code": code,
            "new_password": "ResetPassword2026!#"
        })
        assert reset_resp.status_code == 200
        assert reset_resp.json()["ok"] is True

        # 10. Login with Reset Password
        login_post_reset = await client.post("/api/login", json={
            "email": "tester@ocean.org",
            "password": "ResetPassword2026!#"
        })
        assert login_post_reset.status_code == 200
        assert login_post_reset.json()["ok"] is True
