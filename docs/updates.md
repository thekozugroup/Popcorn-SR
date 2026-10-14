# Container updates

Atlas uses Unraid's existing Docker update controls. Spark uses a small host service that the worker can ask to update itself. No additional updater container is needed. Only verified, published `stable` releases become automatic updates; a source commit or Git push alone does not deploy untested code.

## Unraid

Use a Docker Manager template with repository `ghcr.io/thekozugroup/popcorn-sr:stable` after that tag is published and anonymously verified. In the existing **CA Auto Update Applications** settings, enable Popcorn-SR alongside the containers already selected. Preserve the existing schedule, other selections and notification settings. The plugin pulls the image and recreates the manager using its saved template. Library originals remain read-only; the database and finished-copy folders stay mounted.

An interrupted network job is marked failed and can be retried. Schedule manager updates when the library queue is idle. This uses the installed Unraid plugin rather than adding a sidecar or a second update schedule. Locally loaded release-kit tags do not receive registry updates.

## Linux / DGX Spark

The worker update protocol requires 0.4.0 or later on manager and worker. It is opt-in. A worker without a configured host service continues using ordinary Docker/Compose updates.

Install the host files under `/opt/popcorn-sr`, owned by root and not writable by the worker: `update-worker.py` from `scripts/`, a resolved Compose file containing only the `worker` service, private `worker.env`, and `update.json`. The resolved Compose configuration must retain an image variable (`POPCORN_NGX_IMAGE`, `POPCORN_AI_IMAGE` or `POPCORN_IMAGE`) rather than bake in the current image. Keep the container's default unique hostname. Preserve the existing worker state, initialized scratch folder and read-only SDK/driver mounts. Layer `compose.updates.yaml` over the worker configuration: it mounts only `/var/lib/popcorn-sr/updates` at `/updates` and opts this worker out of other Watchtower updates.

Create the control folder owned by the worker's numeric UID/GID, with mode 0700. The app receives no Docker socket, privileged mode or host configuration mount. The host service operates only the configured Compose project and `worker` service. Example `update.json`:

```json
{
  "role": "ngx",
  "project": "popcorn-sr-spark",
  "compose": "/opt/popcorn-sr/worker.yaml",
  "environment": "/opt/popcorn-sr/worker.env",
  "control": "/var/lib/popcorn-sr/updates",
  "automatic": true,
  "validation_seconds": 1200
}
```

Use role `ngx` for the native worker (`ngx-stable`), `cpu` for the base image (`stable`) or `ai` only when a public `ai-stable` image exists. All roles use the fixed public `ghcr.io/thekozugroup/popcorn-sr` package. SDKs, models, host drivers and Docker's own storage location are provisioned separately.

Install the three files in `systemd/` under `/etc/systemd/system/`, reload systemd, then enable the path and timer:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now popcorn-sr-worker-update.path popcorn-sr-worker-update.timer
```

The host service runs each minute to renew its availability and finish pending idle replacements; registry release checks occur every six hours. **Devices & storage → Check for updates** requests an immediate check. From inside the running worker container, the equivalent command is:

```sh
popcorn-sr request-update
```

The host stages the release, signals the worker to finish its current job, then waits for a fresh idle acknowledgement from that exact container. No new job is claimed during replacement. It preserves pairing and all configured paths, recreates only the worker with an immutable digest and waits for genuine startup tests. An update must retain previously verified codecs, enhancements and processing combinations. Failed checks restore and validate the exact previous image. That failed revision is not automatically retried; the UI permits a manual retry. The previous image remains available for recovery.

Check host failures with `journalctl -u popcorn-sr-worker-update.service`. If rollback itself fails, the worker remains paused and the UI reports failure: fix the mount/runtime before resuming. Do not delete a drain file while a replacement is in progress. Updates can write image layers into Docker's data directory; moving video scratch to Optane does not move those layers or host swap. The small host controller is a separately installed, fixed component; protocol changes require its explicit replacement.

Version 0.4.1 is installed on Atlas and Spark. Atlas's native template points to the public `stable` channel; only Popcorn-SR was added to its existing daily update selection and boot list. Other containers, settings and services were preserved. Spark's path/timer are enabled, and an update request from inside its running container successfully reports the published current version. Its manually installed release passed fresh genuine GPU startup and paired returns.

Unit/API checks, twelve browser workflows and a real CPU-container replacement/rollback trial pass. The replacement trial uses explicit local registry staging and a prior-version fixture; it preserves an active job, queued work, pairing, originals and storage paths. A published-release GPU replacement was not exercised. Run `uv run python scripts/docker-update-smoke.py --image YOUR_TEST_IMAGE --report evidence/NEW_RECEIPT.json` against an explicitly selected isolated Docker host. [Public acceptance and exact boundaries](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.1/acceptance.json).
