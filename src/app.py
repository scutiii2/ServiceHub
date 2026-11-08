"""ServiceHub: one admin page that lists registered model/tool services and shows each admin UI in an iframe.

Registry lives in a JSON file. Health = GET <url>/health. /s/<id>/... reverse-proxies to the service
so the browser only talks to the hub (one port, no mixed content, no frame-header problems).
"""
import asyncio
import hmac
import json
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import uvicorn
from docker.errors import DockerException
import docker
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from starlette.background import BackgroundTask

DATA_FILE = Path(os.environ.get("HUB_DATA", "data/services.json"))
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
PORT = int(os.environ.get("HUB_PORT", "29880"))
ADMIN_PASSWORD = os.environ.get("HUB_ADMIN_PASSWORD", "")  # guards start/stop/restart only; empty = control disabled
HEALTH_TIMEOUT = 6.0  # MiniCPM /health takes ~2 s while Ollama is down
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "upgrade", "proxy-authorization",
       "proxy-authenticate", "trailers", "host", "content-length"}


class ServiceIn(BaseModel):
    name: str
    url: str  # base URL of the service, e.g. http://192.168.1.10:29202
    admin_path: str = "/admin/"
    direct: bool = False  # True = iframe straight to the URL instead of through the hub proxy
    container: str = ""  # Docker container name or compose project to start/stop/restart; empty = no control

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("url must be http(s)://host[:port]")
        return v

    @field_validator("admin_path")
    @classmethod
    def _path(cls, v: str) -> str:
        return "/" + v.strip().lstrip("/")

    @field_validator("container")
    @classmethod
    def _container(cls, v: str) -> str:
        return v.strip()

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name required")
        return v


class DockerControl:
    """Start/stop/restart containers through the mounted Docker socket, like Citadel's server_manager.

    `target` is an exact container name, else a compose project (every container of it, so replicas and
    their load balancer move together). Only targets taken from the registry reach this class.
    The SDK is blocking, so every call runs in a worker thread.
    """

    ACTIONS = ("start", "stop", "restart")

    def _client(self) -> docker.DockerClient:
        try:
            return docker.from_env()
        except DockerException as e:
            raise HTTPException(503, f"Docker unreachable (mount /var/run/docker.sock): {e}")

    @staticmethod
    def _resolve(client: docker.DockerClient, target: str) -> tuple[str, list]:
        """('container', [c]) for an exact name, else ('compose', members of that project)."""
        try:
            return "container", [client.containers.get(target)]
        except docker.errors.NotFound:
            members = client.containers.list(all=True, filters={"label": f"com.docker.compose.project={target}"})
            return ("compose" if members else "missing"), members

    @staticmethod
    def _info(kind: str, containers: list) -> dict:
        states = {c.status for c in containers}
        state = "missing" if not states else states.pop() if len(states) == 1 else "partial"
        return {"kind": kind, "state": state, "members": sorted(c.name for c in containers)}

    def _infos(self, targets: list[str]) -> dict[str, dict]:
        unknown = {"kind": "unknown", "state": "unknown", "members": []}
        try:
            client = self._client()
            return {t: self._info(*self._resolve(client, t)) for t in targets}
        except (HTTPException, DockerException):
            return {t: unknown for t in targets}

    def _act(self, target: str, action: str) -> dict:
        client = self._client()
        try:
            kind, containers = self._resolve(client, target)
            if not containers:
                raise HTTPException(404, f"no container or compose project named {target!r}")
            for c in containers:
                getattr(c, action)()
                c.reload()
        except DockerException as e:
            raise HTTPException(502, f"docker {action} failed: {e}")
        return self._info(kind, containers)

    async def infos(self, targets: list[str]) -> dict[str, dict]:
        return await asyncio.to_thread(self._infos, targets) if targets else {}

    async def act(self, target: str, action: str) -> dict:
        return await asyncio.to_thread(self._act, target, action)


class Registry:
    """JSON-file store. Single process; writes are atomic via replace."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()

    def load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return []

    def _save(self, items: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=2), "utf-8")
        tmp.replace(self.path)

    async def add(self, svc: ServiceIn) -> dict:
        async with self._lock:
            items = self.load()
            item = {"id": uuid.uuid4().hex[:8], **svc.model_dump()}
            self._save(items + [item])
            return item

    async def update(self, sid: str, svc: ServiceIn) -> dict:
        async with self._lock:
            items = self.load()
            for i, it in enumerate(items):
                if it["id"] == sid:
                    items[i] = {"id": sid, **svc.model_dump()}
                    self._save(items)
                    return items[i]
        raise HTTPException(404, "unknown service")

    async def remove(self, sid: str) -> None:
        async with self._lock:
            items = self.load()
            kept = [i for i in items if i["id"] != sid]
            if len(kept) == len(items):
                raise HTTPException(404, "unknown service")
            self._save(kept)

    def get(self, sid: str) -> dict:
        for it in self.load():
            if it["id"] == sid:
                return it
        raise HTTPException(404, "unknown service")


def create_app(registry: Registry | None = None, client: httpx.AsyncClient | None = None,
               control: DockerControl | None = None, password: str | None = None) -> FastAPI:
    secret = ADMIN_PASSWORD if password is None else password
    reg = registry or Registry(DATA_FILE)
    ctl = control or DockerControl()
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=HEALTH_TIMEOUT), follow_redirects=False)
    app = FastAPI(title="ServiceHub", docs_url=None, redoc_url=None)

    async def health(svc: dict) -> dict:
        try:
            r = await http.get(svc["url"] + "/health", timeout=HEALTH_TIMEOUT)
            return {**svc, "up": r.status_code < 500}
        except httpx.HTTPError:
            return {**svc, "up": False}

    @app.get("/api/services")
    async def list_services():
        items = reg.load()
        rows, infos = await asyncio.gather(
            asyncio.gather(*(health(s) for s in items)),
            ctl.infos([s["container"] for s in items if s.get("container")]),
        )
        return [{**r, **(infos.get(r.get("container", "")) or {"kind": None, "state": None, "members": []})}
                for r in rows]

    @app.get("/api/config")
    async def config():
        return {"control_enabled": bool(secret)}

    @app.post("/api/services/{sid}/{action}")
    async def control_service(sid: str, action: str, request: Request):
        if action not in DockerControl.ACTIONS:
            raise HTTPException(404, "unknown action")
        if not secret:
            raise HTTPException(403, "control disabled: set HUB_ADMIN_PASSWORD on the hub")
        if not hmac.compare_digest(request.headers.get("x-hub-password", "").encode(), secret.encode()):
            await asyncio.sleep(1)  # slows password guessing
            raise HTTPException(401, "wrong password")
        target = reg.get(sid).get("container")
        if not target:
            raise HTTPException(400, "no container configured for this service")
        return await ctl.act(target, action)

    @app.post("/api/services", status_code=201)
    async def add_service(svc: ServiceIn):
        return await reg.add(svc)

    @app.put("/api/services/{sid}")
    async def edit_service(sid: str, svc: ServiceIn):
        return await reg.update(sid, svc)

    @app.delete("/api/services/{sid}", status_code=204)
    async def delete_service(sid: str):
        await reg.remove(sid)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.api_route("/s/{sid}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def proxy(sid: str, path: str, request: Request):
        base = reg.get(sid)["url"]
        target = f"{base}/{path}"
        if request.url.query:
            target += "?" + request.url.query
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP | {"origin", "referer"}}
        try:
            up = await http.send(
                http.build_request(request.method, target, headers=headers, content=request.stream()),
                stream=True,
            )
        except httpx.HTTPError as e:
            raise HTTPException(502, f"service unreachable: {e.__class__.__name__}")
        out = {k: v for k, v in up.headers.items() if k.lower() not in HOP | {"x-frame-options"}}
        loc = out.get("location")
        if loc and loc.startswith(base):  # keep redirects inside the proxy
            out["location"] = f"/s/{sid}" + loc[len(base):]
        elif loc and loc.startswith("/") and not re.match(r"^/s/", loc):
            out["location"] = f"/s/{sid}{loc}"
        return StreamingResponse(up.aiter_raw(), status_code=up.status_code, headers=out,
                                 background=BackgroundTask(up.aclose))

    @app.get("/")
    async def index():
        return FileResponse(WEB_DIR / "index.html")

    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT)
