from fastapi import Request
from uuid import uuid4

async def get_session_key(request: Request) -> str:
    """
    Dependency that gets the session_key from the signed cookie.
    If it doesn't exist, it generates a new one and stores it in the session.
    """
    if "session_key" not in request.session:
        request.session["session_key"] = uuid4().hex
    return request.session["session_key"]