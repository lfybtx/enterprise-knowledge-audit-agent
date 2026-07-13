from typing import Optional

import pytest
from fastapi import Header, HTTPException

import app.main as main


TEST_USERS = {
    "admin": ("Admin", "admin"),
    "local-demo": ("Local Demo", "owner"),
    "demo-alice": ("Alice", "editor"),
    "demo-bob": ("Bob", "viewer"),
}


def mock_authenticated_user(
    user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> main.AuthenticatedUser:
    if not user_id:
        raise HTTPException(status_code=401, detail="Login is required")
    account = TEST_USERS.get(user_id)
    if account is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return main.AuthenticatedUser(id=user_id, display_name=account[0], role=account[1])


@pytest.fixture(autouse=True)
def override_authentication():
    main.app.dependency_overrides[main.get_authenticated_user] = mock_authenticated_user
    yield
    main.app.dependency_overrides.pop(main.get_authenticated_user, None)
