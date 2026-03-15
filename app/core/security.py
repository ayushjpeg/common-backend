from fastapi import Request


def require_api_key(request: Request) -> None:
    if request.method == "OPTIONS":
        return
