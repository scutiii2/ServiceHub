# Deploying ServiceHub

ServiceHub is one Docker container on port 29880. It runs on the always-on deployment machine (default `lex@scutiserver1.local`, folder `/media/ZimaOS-HD/Apps/Applications/ServiceHub`) and you open it through one Zima app.

## Requirements on the machine

- Docker with Compose v2.
- ssh access as the normal user (root over ssh is refused).
- The model and tool services reachable from the machine by URL (their LAN address and port, or `http://host.docker.internal:<port>` for services on the same Docker host).
- For Start / Stop / Restart: the Docker socket (`docker-compose.yml` already mounts `/var/run/docker.sock`) and `HUB_ADMIN_PASSWORD` in `.env`.

## 1. Publish the code (from your PC)

Commit `main` first: publish reads committed `main`. Then run `run.bat deploy`:

| Option | Does |
|---|---|
| 1 | Publish code to the `live` branch |
| 2 | Copy your `.env` to the server (one ssh/tar session, one password prompt) |
| 3 | Both |
| 4, 5 | Dry runs of 1 and 2 |
| 6 | chown helper, if option 2 says `Permission denied` |
| R | Release: publish, then tag `VERSION` |

Keep your own target in the git-ignored `tools\deploy.local.ini` (copy `tools\deploy.local.example.ini`), or set `DEPLOY_HOST`, `DEPLOY_DIR` and `DEPLOY_WEB_PORT` before running.

## 2. First-time setup on the machine

```bash
mkdir -p /media/ZimaOS-HD/Apps/Applications
git clone -b live https://github.com/scutiii2/ServiceHub.git /media/ZimaOS-HD/Apps/Applications/ServiceHub
cd /media/ZimaOS-HD/Apps/Applications/ServiceHub
cp .env.example .env   # set HUB_ADMIN_PASSWORD (deploy option 2 copies yours instead)
```

## 3. Start

```bash
docker compose up -d --build
curl http://127.0.0.1:29880/healthz
```

Then add one app in the Zima dashboard (custom app, web UI `http://<device-ip>:29880`) and register each service in the hub sidebar.

## Updating

```bash
cd /media/ZimaOS-HD/Apps/Applications/ServiceHub
git pull
docker compose up -d --build
```

The registry (`/data/services.json`) lives in the `servicehub_data` volume and survives rebuilds.

## Releasing

A plain publish only updates `live`. For a release set `VERSION` (and `pyproject.toml` to the same number), commit, then run `run.bat deploy`, option R, or `py tools\publish_live.py --release`.

## Problems

- Hub shows a service red: the machine cannot reach its URL. Use the LAN IP, not `127.0.0.1` (inside the container that is the hub itself).
- Start / Stop / Restart say "control disabled": set `HUB_ADMIN_PASSWORD` in `.env` and run `docker compose up -d`.
- "Docker unreachable": the socket mount is missing or the user cannot read it.
