# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Existing: FastAPI backend serving one static `web/index.html` (vanilla JS, no build step). Mockup is a standalone static HTML file.

## Users
Solo owner running a home ZimaOS device with model and tool services in Docker. Opens a service's admin UI, glances at health, occasionally starts/stops/restarts a container. LAN only.

## Product Purpose
One Zima app that lists registered model/tool services by URL, shows health, and opens each service's admin UI in an iframe through a reverse proxy. Success: any service's admin page is one click away; risky container actions are deliberate.

## Positioning
Single hub for a workspace's services with Docker-aware Start/Stop/Restart (container vs compose project) and one-click Discover of containers on the same host.

## Operating Context
Used in a browser tab opened from the Zima dashboard. Sidebar of services; main area is the embedded admin UI. Password is asked only for Start/Stop/Restart.

## Capabilities and Constraints
Health dots; `container`/`compose` tag; closeable risk warning listing affected containers; add/edit/delete service; Discover tab with Add buttons and a /health filter; password prompt for control actions. Mockup uses synthetic data only.

## Brand Commitments
Direction pinned by user: clean, light and airy with lots of whitespace, minimal chrome with content first, dark mode as well.

## Evidence on Hand
Current UI in `web/index.html`. No logo or brand assets.

## Product Principles
1. The embedded admin UI is the product; the hub frame should recede.
2. Dangerous actions are deliberate, never ambient.
3. State (up, down, container, compose) readable at a glance.
4. Adding a service takes seconds.
