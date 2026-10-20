"""Other devices on the network: where the server listens, and who may come in.

The desktop app serves the UI on ``127.0.0.1``. With the network switch on (Settings → Network, per
computer, off by default) the same app is also served on every IPv4 address of this computer's network
adapters, on one fixed port (``NetworkSettings.port``). The port is never moved: when something else has
it, ``status()["error"]`` says so and the switch keeps trying.

- ``Network.sync()`` makes the listeners match the settings (one small uvicorn server per address, started
  and stopped while the app runs, so the switch applies without a restart). A background thread repeats it,
  so a wifi that comes and goes, or a program that gives the port back, is picked up.
- ``NetworkGate`` is an ASGI middleware around the whole app (HTTP and websocket). A request from this
  computer always passes. Any other request is refused while the switch is off, and, when a PIN is set,
  until the device has entered it once (a signed cookie, ``COOKIE``). ``/_pin`` is the only address a
  device without the cookie reaches.

The PIN keeps casual visitors off a shared wifi; it isn't strong security (the traffic is not encrypted).
"""

from __future__ import annotations

import errno
import hmac
import html
import ipaddress
import logging
import secrets
import socket
import sys
import threading
import time
from http.cookies import SimpleCookie
from typing import Callable
from urllib.parse import parse_qs

import uvicorn
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from ..config.models import NetworkSettings

log = logging.getLogger(__name__)

COOKIE = "pitchcontrol_pin"
COOKIE_DAYS = 30
PIN_PATH = "/_pin"
SYNC_SECONDS = 5.0  # how often the listeners are matched to the settings and the adapters
FAILS_BEFORE_LOCK = 5  # wrong PINs from one address before it must wait
LOCK_SECONDS = 30.0  # the first wait; it doubles with every further lock, up to LOCK_MAX_SECONDS
LOCK_MAX_SECONDS = 900.0

PORT_BUSY_ERRNOS = {errno.EADDRINUSE, errno.EACCES, 10048, 10013}  # the last two: Windows


# ---------------------------------------------------------------------------- addresses


def adapter_addresses() -> list[tuple[str, str]]:
    """``(adapter name, IPv4 address)`` of every network adapter that has one, except loopback and
    link-local (169.254.x.x, an adapter without a network)."""
    found: list[tuple[str, str]] = []
    try:
        import ifaddr

        for adapter in ifaddr.get_adapters():
            for ip in adapter.ips:
                if ip.is_IPv4 and isinstance(ip.ip, str):
                    found.append((adapter.nice_name or adapter.name, ip.ip))
    except Exception:  # noqa: BLE001
        log.exception("listing the network adapters failed: using the host name's addresses")
        try:
            found = [("This computer", a) for a in socket.gethostbyname_ex(socket.gethostname())[2]]
        except OSError:
            pass
    out: list[tuple[str, str]] = []
    for name, addr in found:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or any(addr == a for _, a in out):
            continue
        out.append((name, addr))
    return out


def _normal(host: str) -> str:
    host = host.split("%", 1)[0]  # an IPv6 zone
    return host.removeprefix("::ffff:")  # an IPv4 address as a dual-stack socket reports it


# ---------------------------------------------------------------------------- listeners


class _Listener:
    def __init__(self, address: str, port: int, server: uvicorn.Server, thread: threading.Thread):
        self.address, self.port, self.server, self.thread = address, port, server, thread

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _port_in_use_message(port: int, exc: OSError | None = None) -> str:
    if exc is None or exc.errno in PORT_BUSY_ERRNOS:
        return f"Port {port} is already used by another program. Close that program or choose another port: PitchControl never moves to a different one by itself."
    return f"Can't listen on port {port}: {exc.strerror or exc}"


class Network:
    """The network listeners of one app, and the access rules the gate applies."""

    def __init__(
        self,
        app,
        get_settings: Callable[[], NetworkSettings],
        addresses: Callable[[], list[tuple[str, str]]] = adapter_addresses,
        interval: float = SYNC_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.app = app
        self.get_settings = get_settings
        self.addresses = addresses
        self.interval = interval
        self.clock = clock
        self._key = secrets.token_bytes(32)  # cookies of an earlier run don't count: a restart asks the PIN again
        self._lock = threading.Lock()
        self._listeners: dict[str, _Listener] = {}
        self._errors: dict[str, str] = {}
        self._adapters: list[tuple[str, str]] = []
        self._own: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._attempts: dict[str, list[float]] = {}  # address -> [wrong PINs in a row, locked until, locks so far]

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Begin matching the listeners to the settings (and keep doing it)."""
        if self._thread is not None:
            return
        self.sync()
        self._thread = threading.Thread(target=self._watch, name="network", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._stop_listeners(list(self._listeners))
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _watch(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.sync()
            except Exception:  # noqa: BLE001
                log.exception("updating the network listeners failed")

    # ------------------------------------------------------------ listening
    def sync(self) -> None:
        """Make the listeners match the settings and this computer's addresses now."""
        with self._lock:
            if self._stop.is_set():
                return
            cfg = self.get_settings()
            self._adapters = self.addresses()
            self._own = {a for _, a in self._adapters}
            wanted = [a for _, a in self._adapters] if cfg.enabled else []
            self._stop_listeners([a for a, l in self._listeners.items() if a not in wanted or l.port != cfg.port or not l.thread.is_alive()])
            self._errors = {a: e for a, e in self._errors.items() if a in wanted}
            for address in wanted:
                if address in self._listeners:
                    continue
                try:
                    self._listeners[address] = self._listen(address, cfg.port)
                    self._errors.pop(address, None)
                    log.info("other devices can use http://%s:%d", address, cfg.port)
                except OSError as exc:
                    if address not in self._errors:
                        log.warning("not listening on %s:%d: %s", address, cfg.port, exc)
                    self._errors[address] = _port_in_use_message(cfg.port, exc)

    def _stop_listeners(self, addresses: list[str]) -> None:
        for address in addresses:
            listener = self._listeners.pop(address, None)
            if listener is not None:
                listener.stop()
                log.info("no longer listening on %s:%d", address, listener.port)

    def _listen(self, address: str, port: int) -> _Listener:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:  # something that answers has the port already
            probe.settimeout(0.5)
            if probe.connect_ex((address, port)) == 0:
                raise OSError(errno.EADDRINUSE, "the port answers")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sys.platform == "win32":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # no sharing the port with another program
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((address, port))
        except OSError:
            sock.close()
            raise
        server = uvicorn.Server(uvicorn.Config(self.app, log_level="warning", timeout_graceful_shutdown=1))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, name=f"server {address}", daemon=True)
        thread.start()
        return _Listener(address, port, server, thread)

    # ------------------------------------------------------------ what the UI shows
    def status(self) -> dict:
        cfg = self.get_settings()
        with self._lock:
            listening = {a for a, l in self._listeners.items() if l.thread.is_alive()}
            error = next(iter(self._errors.values()), None) if cfg.enabled and not listening else None
            adapters = list(self._adapters) if cfg.enabled else []
        return {
            "enabled": cfg.enabled,
            "port": cfg.port,
            "pin": cfg.pin,
            "listening": bool(listening),
            "error": error,
            "addresses": [{"name": n, "ip": a, "url": f"http://{a}:{cfg.port}", "listening": a in listening} for n, a in adapters],
        }

    # ------------------------------------------------------------ access
    def is_local(self, host: str | None) -> bool:
        """This computer: loopback, one of its own addresses, or no network address at all (a unix socket, a test client)."""
        if not host:
            return True
        host = _normal(host)
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return True  # not an address of the network: nobody else can have it
        return ip.is_loopback or host in self._own

    def token(self, pin: str) -> str:
        """What the cookie holds: it stops fitting when the PIN is changed."""
        return hmac.new(self._key, f"pin:{pin}".encode(), "sha256").hexdigest()

    def cookie_ok(self, headers: list[tuple[bytes, bytes]], pin: str) -> bool:
        raw = next((v.decode("latin-1") for k, v in headers if k == b"cookie"), "")
        try:
            jar = SimpleCookie(raw)
        except Exception:  # noqa: BLE001
            return False
        morsel = jar.get(COOKIE)
        return morsel is not None and hmac.compare_digest(morsel.value, self.token(pin))

    def locked_for(self, host: str) -> int:
        """Seconds this address must wait before it may try a PIN again (0 = it may)."""
        entry = self._attempts.get(host)
        return max(0, int(entry[1] - self.clock()) + 1) if entry and entry[1] > self.clock() else 0

    def wrong_pin(self, host: str) -> None:
        if len(self._attempts) > 500:  # a scan from many addresses must not grow this without end
            self._attempts.clear()
        entry = self._attempts.setdefault(host, [0.0, 0.0, 0.0])
        entry[0] += 1
        if entry[0] >= FAILS_BEFORE_LOCK:
            entry[2] += 1
            entry[0] = 0
            entry[1] = self.clock() + min(LOCK_SECONDS * 2 ** (entry[2] - 1), LOCK_MAX_SECONDS)

    def right_pin(self, host: str) -> None:
        self._attempts.pop(host, None)


# ---------------------------------------------------------------------------- the gate

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PitchControl</title>
<style>
html,body{{margin:0;height:100%;background:#0e0f12;color:#d8d9d4;font-family:ui-monospace,Menlo,Consolas,monospace}}
body{{display:grid;place-items:center}}
main{{width:min(320px,86vw)}}
h1{{font-size:14px;letter-spacing:.2em;text-transform:uppercase;font-weight:500;margin:0 0 18px}}
p{{font-size:12px;line-height:1.5;color:#8a8c87;margin:0 0 14px}}
p.bad{{color:#e0794f}}
input,button{{font:inherit;font-size:22px;width:100%;box-sizing:border-box;height:52px;margin:0 0 10px;background:#15171a;color:inherit;border:1px solid #2a2d31;border-radius:0;text-align:center;letter-spacing:.3em}}
button{{letter-spacing:.15em;font-size:13px;text-transform:uppercase;cursor:pointer}}
input:focus,button:hover{{outline:none;border-color:#d8d9d4}}
</style></head><body><main>
<h1>PitchControl</h1>
{body}
</main></body></html>"""

FORM = """<form method="post" action="/_pin">
<p>{message}</p>
<input name="pin" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="8" autocomplete="off" autofocus aria-label="PIN">
<button type="submit">Open</button>
</form>"""


def pin_page(message: str = "Enter the PIN to control the lights from this device.", bad: bool = False, status: int = 401) -> HTMLResponse:
    text = html.escape(message)
    body = FORM.format(message=text).replace("<p>", '<p class="bad">' if bad else "<p>", 1)
    return HTMLResponse(PAGE.format(body=body), status_code=status, headers={"Cache-Control": "no-store"})


class NetworkGate:
    """ASGI middleware: tells the app whether a request comes from this computer (``scope["pc_local"]``) and
    refuses the other ones as the network settings say."""

    def __init__(self, app, network: Network):
        self.app = app
        self.network = network

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        net = self.network
        host = (scope.get("client") or (None, 0))[0]
        local = net.is_local(host)
        scope["pc_local"] = local
        if local:
            await self.app(scope, receive, send)
            return

        cfg = net.get_settings()
        path = scope.get("path", "")
        web = scope["type"] == "http"
        api = path.startswith("/api/") or not web

        async def refuse(status: int, detail: str, page: Response | None = None) -> None:
            if not web:
                await send({"type": "websocket.close", "code": 1008})
                return
            await (JSONResponse({"detail": detail}, status_code=status) if api else (page or Response(detail, status_code=status)))(scope, receive, send)

        if not cfg.enabled:
            await refuse(403, "Other devices are not allowed: turn on 'Allow other devices on this network' in PitchControl's Settings.")
            return
        if cfg.pin and not net.cookie_ok(scope.get("headers") or [], cfg.pin):
            if web and path == PIN_PATH:
                await self._pin_request(scope, receive, send, host, cfg.pin)
            else:
                await refuse(401, "PIN needed", pin_page())
            return
        await self.app(scope, receive, send)

    async def _pin_request(self, scope, receive, send, host: str, pin: str) -> None:
        net = self.network
        if scope["method"] != "POST":
            await pin_page()(scope, receive, send)
            return
        wait = net.locked_for(host)
        if wait:
            await pin_page(f"Too many wrong PINs. Try again in {wait} seconds.", bad=True, status=429)(scope, receive, send)
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body") or len(body) > 1024:
                break
        given = (parse_qs(body[:1024].decode("utf-8", "replace")).get("pin") or [""])[0].strip()
        if given and hmac.compare_digest(given.encode(), pin.encode()):
            net.right_pin(host)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(COOKIE, net.token(pin), max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax", path="/")
            await response(scope, receive, send)
            return
        net.wrong_pin(host)
        log.warning("a wrong PIN from %s", host)
        await pin_page("That is not the PIN.", bad=True)(scope, receive, send)

