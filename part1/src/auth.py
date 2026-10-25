"""Access gate for requests that arrive from outside this laptop (through the Cloudflare tunnel).

Requests from the laptop itself (127.0.0.1) pass untouched. A request counts as remote when it carries
the headers a proxy adds (cloudflared sets Cf-Connecting-Ip), or comes from a non-loopback address.
A remote request needs the ACCESS_TOKEN from inputs/.env: open the link once with ?key=TOKEN and the
browser keeps it in a cookie. With no ACCESS_TOKEN set, remote requests are refused outright.
"""
import hmac
import ipaddress
from http.cookies import SimpleCookie
from urllib.parse import parse_qsl, urlencode

from src import config

COOKIE = "atoll_key"
PROXY_HEADERS = (b"cf-connecting-ip", b"x-forwarded-for", b"cf-ray")


def is_remote(scope) -> bool:
    headers = dict(scope["headers"])
    if any(h in headers for h in PROXY_HEADERS):
        return True
    client = scope.get("client")
    try:
        return not ipaddress.ip_address(client[0]).is_loopback if client else False
    except ValueError:  # not an IP address (no real socket behind it): treat as local
        return False


def _matches(candidate: str | None, token: str) -> bool:
    return bool(candidate) and hmac.compare_digest(candidate.encode(), token.encode())


class AccessGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not is_remote(scope):
            return await self.app(scope, receive, send)

        token = config.ACCESS_TOKEN
        headers = dict(scope["headers"])
        cookie = SimpleCookie(headers.get(b"cookie", b"").decode("latin-1"))
        if token and COOKIE in cookie and _matches(cookie[COOKIE].value, token):
            return await self.app(scope, receive, send)

        if token and scope["type"] == "http" and scope["method"] == "GET":
            query = parse_qsl(scope["query_string"].decode("latin-1"))
            if _matches(dict(query).get("key"), token):  # first visit from the link: remember it, drop it from the URL
                rest = urlencode([(k, v) for k, v in query if k != "key"])
                secure = "; Secure" if headers.get(b"x-forwarded-proto") == b"https" else ""
                await send({"type": "http.response.start", "status": 303, "headers": [
                    (b"location", (scope["path"] + (f"?{rest}" if rest else "")).encode()),
                    (b"set-cookie", f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{secure}".encode()),
                    (b"cache-control", b"no-store")]})
                return await send({"type": "http.response.body", "body": b""})

        if scope["type"] == "websocket":
            await receive()  # the connect message
            return await send({"type": "websocket.close", "code": 1008})
        message = (b"Not authorised. Open the link printed by run.py --tunnel (it ends in ?key=...)." if token
                   else b"Remote access is off: ACCESS_TOKEN is not set in inputs/.env.")
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"text/plain"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": message})
