# ServiceHub

One admin web page for all model and tool services. Sidebar lists registered services with a health dot; the selected service's admin UI loads in an iframe. Port 29880 (workspace block 29600–29899).

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv`, managed by uv)
- Install: `uv sync`
- Test: `uv run pytest -q`
- Run: `run.bat`, or `uv run python src/app.py`, or `docker compose up -d --build`

## Rules
- `src/app.py` is the whole backend: JSON registry (`HUB_DATA`, default `data/services.json`), health = `GET <url>/health`, reverse proxy at `/s/<id>/...`.
- Services must use relative URLs in their admin UI (all current ones do) or the proxy breaks them; "direct" mode skips the proxy.
- Start/stop/restart (`DockerControl`) uses the mounted Docker socket, like Citadel's server_manager. Nothing is configured per service: the container is the one publishing the URL's port (`HostConfig.PortBindings`); if it has a `com.docker.compose.project` label the whole project is the target. Relies on unique ports per service (workspace rule). Services outside Docker get no controls.
- Auth only on `POST /api/services/{id}/{start|stop|restart}`: header `X-Hub-Password` must equal `HUB_ADMIN_PASSWORD`; empty env = control disabled (403). Everything else is open (LAN only): anyone can register a URL the hub will fetch. The Docker socket is root-equivalent on the host.
- UI: a closeable warning shows each time a service backed by a container is selected; compose warnings list all affected containers.
- No websocket proxying. Add it only if a service admin needs one.
- Deploy: same flow as the tool services. `py tools\publish_live.py` pushes only the deploy paths to the `live` branch; the device clones `live` and runs `docker compose up -d --build`. `run.bat deploy` also copies `.env`. Add a path to `DEPLOY_PATHS` when the image needs a new file. Details: `deployment.md`.
- Commit with the noreply author email `214214011+scutiii2@users.noreply.github.com` (another address is rejected on push). Push `main`, then run `py tools\publish_live.py`.
