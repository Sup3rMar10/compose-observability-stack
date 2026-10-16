# 📈 Compose Observability Stack

> **Reference configuration.** Written to show the setup; it has not been run or tested end to end. Only `docker compose config` was used to check that the compose file parses (and a JSON and Python syntax check on the dashboard and the app).

A small Docker Compose stack that shows the usual first step of running a service for a customer: make it measurable. A tiny app exposes Prometheus metrics, Prometheus scrapes it and evaluates one alert, Grafana shows a provisioned dashboard, and Alertmanager receives the alert.

This is original code. The app is about 100 lines of standard-library Python.

```
 you ── curl ──▶ app :8000 (127.0.0.1)          Grafana :3000 (127.0.0.1) ◀── browser
                  │  /work  /healthz  /metrics        │
                  │                                   │ queries
                  └──────── scraped every 15 s ──▶ Prometheus :9090 (127.0.0.1)
                                                      │ evaluates alerts.yml
                                                      ▼
                                                 Alertmanager :9093 (internal only, no notifications configured)

 networks: backend (internal: true) carries service-to-service traffic
           frontend carries only the published 127.0.0.1 ports
```

## What each file does

| File | What it is |
|---|---|
| `app/server.py`, `app/Dockerfile` | Demo service. `/work` fails on purpose for 20% of requests (`FAIL_RATE`). `/metrics` has a request counter and a latency histogram. `/healthz` is excluded from the metrics. Non-root user, root-owned code. |
| `docker-compose.yml` | The stack, with the hardening below. |
| `prometheus/prometheus.yml`, `prometheus/alerts.yml` | Scrape jobs for itself and the app, and one alert: `HighErrorRate` (more than 5% of requests are 5xx for 2 minutes). |
| `alertmanager/alertmanager.yml` | Stub. Receives alerts, sends nothing. |
| `grafana/provisioning/`, `grafana/dashboards/app-overview.json` | The datasource and the dashboard (request rate, error rate, p95 latency) loaded from files, so nothing is clicked together by hand. |
| `.env.example` | Placeholder for the Grafana admin password. `.env` is git-ignored. |

## Why it is set up this way

- **Pinned image tags, no `:latest`.** The same files give the same stack next month. The cost is that somebody has to move the tags forward on purpose.
- **Healthchecks and `depends_on: service_healthy`.** Prometheus waits for the app and Alertmanager, Grafana waits for Prometheus, so start-up order is not luck.
- **Provisioning as code.** The datasource, the dashboard and the alert rule live in git, so the environment can be rebuilt and reviewed like any other change.
- **Two networks.** `backend` is `internal: true`, so a container only on it has no route out; Alertmanager sits there alone. An internal network cannot publish ports, so a second network, `frontend`, exists just for the `127.0.0.1` ports. The app, Prometheus and Grafana are on both, so they are **not** cut off from the internet.
- **Locked-down containers.** All capabilities dropped, `no-new-privileges`, memory, CPU and process limits, and a read-only root filesystem (with `tmpfs` for `/tmp` and a named volume for data) on the app, Prometheus and Alertmanager. Grafana is not read-only because I did not check where else it writes.
- **No secrets in the repo.** The Grafana password is read from `.env`; compose stops with a clear message if it is missing (that error was checked).
- **Ports on `127.0.0.1` only**, because none of these services is meant to be exposed without authentication in front.

## Run it

Needs Docker with Compose v2.

```bash
cp .env.example .env            # then edit the password
docker compose up --build -d
docker compose ps               # all four should become healthy

# make some traffic (about 20% of these return 500)
for i in $(seq 1 200); do curl -s -o /dev/null http://127.0.0.1:8000/work; done

# Grafana:       http://127.0.0.1:3000   (user admin, password from .env), dashboard "App overview" in folder "Demo"
# Prometheus:    http://127.0.0.1:9090   (Alerts tab; HighErrorRate should fire after about 2 minutes of traffic)
docker compose down             # add -v to delete the data volumes
```

## What was and was not checked

- **Checked:** `docker compose config` parses the file and stops with the expected message when the password is unset. The dashboard JSON and `app/server.py` parse. Nothing else.
- **Not checked:** that the pinned image tags exist, that the images build or start, that the healthchecks pass (they rely on `wget` being in the Prometheus, Alertmanager and Grafana images), that read-only filesystems are enough for Prometheus and Alertmanager, that the dashboard queries return data, that the alert fires, that Grafana loads the provisioning, and the Prometheus, Alertmanager and Grafana YAML files were not even syntax-checked (no YAML parser was installed). Treat any of these as a likely first thing to fix.
- **Not covered:** a Linux host (written on Windows with Docker Desktop, not run there either), Docker Swarm or Kubernetes.

## What I would add for a real customer

1. **Retention and storage sizing.** Retention is 7 days here. Size it from their series count and scrape interval, and decide whether Prometheus remote write to long-term storage is needed.
2. **Authentication.** A reverse proxy with login (or SSO in Grafana) before anything leaves localhost, and TLS.
3. **Alert routing.** Real receivers (on-call tool, chat), grouping and silences, and a test that the page actually arrives.
4. **SLOs.** Turn "5% errors for 2 minutes" into an agreed objective with burn-rate alerts, set with the customer.
5. **More signals.** Logs and traces, plus node and container metrics, and alerts for the monitoring stack itself.
6. **A real check.** Bring the stack up in CI, hit the endpoints, and fail the build if the dashboards or alerts do not load.
