import secrets

from fastapi import HTTPException, Request


async def require_api_key(request: Request) -> None:
    expected = request.app.state.settings.gateway_api_key.get_secret_value()
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    valid = (
        bool(expected)
        and scheme.lower() == "bearer"
        and secrets.compare_digest(token.encode(), expected.encode())
    )
    if not valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
