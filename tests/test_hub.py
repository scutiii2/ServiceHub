import httpx
import pytest
from fastapi import FastAPI, HTTPException, Response

from app import DockerControl, Registry, create_app

# Fake upstream service: /health, /admin/ (html), /echo (POST body), redirect.
upstream = FastAPI()


@upstream.get("/health")
async def _h():
    return {"ok": True}


@upstream.get("/admin/")
async def _a():
    return Response("<h1>admin</h1>", media_type="text/html", headers={"X-Frame-Options": "DENY"})


@upstream.post("/echo")
async def _e(body: dict):
    return body


@upstream.get("/go")
async def _g():
    return Response(status_code=302, headers={"location": "/admin/"})


class FakeControl(DockerControl):
    """In-memory containers keyed by published port: no Docker needed."""

    def __init__(self):
        self.state = {1: ("compose", "running")}

    def _info(self, port):
        kind, state = self.state.get(port, ("missing", "missing"))
        return {"kind": kind, "state": state, "members": ["web"] if kind != "missing" else [],
                "project": "proj" if kind == "compose" else None}

    async def infos(self, ports):
        return {p: self._info(p) for p in ports}

    async def act(self, port, action):
        if port not in self.state:
            raise HTTPException(404, "missing")
        self.state[port] = (self.state[port][0], {"start": "running", "stop": "exited", "restart": "running"}[action])
        return self._info(port)


@pytest.fixture
async def hub(tmp_path):
    # One client routed to the fake upstream in-process; the hub uses it for health and proxying.
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=upstream))
    app = create_app(Registry(tmp_path / "s.json"), client, FakeControl(), password="pw")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as c:
        yield c


async def test_register_health_proxy(hub):
    r = await hub.post("/api/services", json={"name": "Up", "url": "http://svc:1/"})
    assert r.status_code == 201
    sid = r.json()["id"]
    await hub.post("/api/services", json={"name": "Down", "url": "http://svc:1"})

    r = await hub.get("/api/services")
    assert [s["up"] for s in r.json()] == [True, True]  # fake upstream answers every host

    r = await hub.get(f"/s/{sid}/admin/")
    assert r.text == "<h1>admin</h1>" and "x-frame-options" not in r.headers

    r = await hub.post(f"/s/{sid}/echo", json={"a": 1})
    assert r.json() == {"a": 1}

    r = await hub.get(f"/s/{sid}/go")
    assert r.headers["location"] == f"/s/{sid}/admin/"


async def test_validation_and_delete(hub):
    assert (await hub.post("/api/services", json={"name": "x", "url": "ftp://x"})).status_code == 422
    sid = (await hub.post("/api/services", json={"name": "x", "url": "http://x:1"})).json()["id"]
    assert (await hub.delete(f"/api/services/{sid}")).status_code == 204
    assert (await hub.delete(f"/api/services/{sid}")).status_code == 404
    assert (await hub.get(f"/s/{sid}/admin/")).status_code == 404


PW = {"X-Hub-Password": "pw"}


async def test_container_control_needs_password(hub):
    sid = (await hub.post("/api/services", json={"name": "c", "url": "http://x:1"})).json()["id"]
    other = (await hub.post("/api/services", json={"name": "p", "url": "http://x:2"})).json()["id"]  # no container
    rows = (await hub.get("/api/services")).json()  # listing, opening and adding need no password
    assert [(r["kind"], r["state"]) for r in rows] == [("compose", "running"), ("missing", "missing")]

    assert (await hub.post(f"/api/services/{sid}/stop")).status_code == 401
    assert (await hub.post(f"/api/services/{sid}/stop", headers={"X-Hub-Password": "bad"})).status_code == 401
    assert (await hub.get("/api/services")).json()[0]["state"] == "running"

    assert (await hub.post(f"/api/services/{sid}/stop", headers=PW)).json()["state"] == "exited"
    assert (await hub.post(f"/api/services/{sid}/restart", headers=PW)).json()["state"] == "running"
    assert (await hub.post(f"/api/services/{sid}/explode", headers=PW)).status_code == 404
    assert (await hub.post(f"/api/services/{other}/start", headers=PW)).status_code == 404


async def test_control_disabled_without_password(tmp_path):
    app = create_app(Registry(tmp_path / "s.json"), httpx.AsyncClient(), FakeControl(), password="")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub") as c:
        sid = (await c.post("/api/services", json={"name": "c", "url": "http://x:1"})).json()["id"]
        assert (await c.get("/api/config")).json() == {"control_enabled": False}
        assert (await c.post(f"/api/services/{sid}/stop", headers=PW)).status_code == 403


class FakeContainer:
    def __init__(self, name, ports=(), project=None, status="running"):
        self.name, self.status = name, status
        self.labels = {DockerControl.PROJECT: project} if project else {}
        self.attrs = {"HostConfig": {"PortBindings": {f"{p}/tcp": [{"HostPort": str(p)}] for p in ports}}}


def test_match_finds_container_or_compose_by_published_port():
    lb = FakeContainer("svc_lb", [29200], "svc")
    api = FakeContainer("svc_api_1", project="svc")
    ollama = FakeContainer("svc_ollama", project="svc", status="exited")
    solo = FakeContainer("solo", [29300])
    allc = [lb, api, ollama, solo, FakeContainer("other", [29400], "other")]

    kind, members = DockerControl._match(allc, 29200)
    assert kind == "compose" and {c.name for c in members} == {"svc_lb", "svc_api_1", "svc_ollama"}
    assert DockerControl._info(kind, members)["state"] == "partial"
    assert DockerControl._match(allc, 29300) == ("container", [solo])
    assert DockerControl._match(allc, 1) == ("missing", [])
