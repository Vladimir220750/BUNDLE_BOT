from fastapi import Request, HTTPException
from ..core.config import settings

async def check_internal_host(request: Request):
    host = request.headers.get("host")
    allowed_hosts = settings.allowed_hosts.split(",")
    if host not in allowed_hosts:
        print(f"Host disallow: host: {host}, allowed: {allowed_hosts}")
        raise HTTPException(status_code=403, detail="Forbidden")

def is_allowed_host(host: str) -> bool:
    allowed_hosts = settings.allowed_hosts.split(",")
    return host in allowed_hosts