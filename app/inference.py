import ipaddress
import socket
from urllib.parse import urlparse

import anyio
import httpx
from rembg import new_session, remove

from app.config import settings

_session = None
_limiter = anyio.CapacityLimiter(settings.max_concurrent_jobs)


def get_model_session():
    global _session
    if _session is None:
        _session = new_session(settings.model_name)
    return _session


def _run_remove(image_bytes: bytes) -> bytes:
    return remove(image_bytes, session=get_model_session())


async def remove_background(image_bytes: bytes) -> bytes:
    return await anyio.to_thread.run_sync(_run_remove, image_bytes, limiter=_limiter)


def _assert_public_host(hostname: str) -> None:
    """Blocks requests to private/loopback/link-local targets to prevent the
    server from being used as an SSRF proxy into the Pi's own network."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host: {hostname}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"Refusing to fetch non-public address: {ip}")


async def fetch_image_from_url(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("image_url must be http or https")
    if not parsed.hostname:
        raise ValueError("image_url is missing a host")

    _assert_public_host(parsed.hostname)

    max_bytes = settings.max_image_mb * 1024 * 1024
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise ValueError(f"Image exceeds {settings.max_image_mb}MB limit")
            return bytes(chunks)
