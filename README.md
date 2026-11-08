# ServiceHub

Central admin UI for the model and tool services. Register each service by URL; click it to open its admin page inside the hub.

- Register: name + base URL (e.g. `http://192.168.1.10:29202`). Admin path defaults to `/admin/`.
- Health dot: `GET <url>/health`, refreshed every 15 s.
- Default mode proxies through the hub (`/s/<id>/...`), so the browser only needs the hub port. Tick "Open directly" to iframe the service URL itself.
- Start / Stop / Restart need no setup: the hub finds the Docker container that publishes the port in the service URL. If it belongs to a compose project, the whole project is the target (replicas, load balancer, Ollama). A tag shows `container` or `compose`, and a closeable warning lists every container affected each time you select the service. Needs `/var/run/docker.sock` (already in `docker-compose.yml`). Services outside Docker, or on another machine, show no controls. Ports must be unique per service.
- Auth: only Start / Stop / Restart ask for a password (`HUB_ADMIN_PASSWORD`; empty = control disabled). Listing, opening and adding services need none.
- Registry is stored in `HUB_DATA` (`data/services.json`; `/data/services.json` in Docker).

## Run
```bash
uv sync
uv run python src/app.py   # http://localhost:29880
```

## Zima
See [deployment.md](deployment.md): publish to the `live` branch with `run.bat deploy`, clone it on the device, `docker compose up -d --build`, then create one Zima app pointing at `http://<zima-ip>:29880`. Register services by the device's LAN IP, or `http://host.docker.internal:<port>` for services on the same Docker host.

## Env
`HUB_PORT` (29880), `HUB_DATA` (registry path), `HUB_ADMIN_PASSWORD` (control password).
