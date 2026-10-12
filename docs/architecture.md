# Architecture

The manager owns library access, credentials, job state and final publication. A worker pulls one compatible job at a time; it never requires a direct library mount. The same protocol works across a LAN and between two services on one host.

```mermaid
sequenceDiagram
  participant UI as Web interface
  participant M as NAS manager
  participant W as Processing worker
  UI->>M: Create one-use pairing code
  W->>M: Exchange code for worker credential
  UI->>M: Inspect source and queue recipe
  W->>M: Claim compatible job and lease
  W->>M: Download source
  W->>W: Verify hash; process on scratch drive
  W->>M: Renew lease and report progress
  W->>W: Validate media; restore source streams
  W->>M: Stream result with checksum
  M->>M: Validate media; publish separate copy
  M->>UI: Completed job and download
```

## Persistence and ownership

SQLite uses WAL and transactions. Pairing codes expire after ten minutes and are consumed exactly once. Worker secrets and browser sessions are hashed in the manager database. The worker retains its secret in an operator-owned state directory. Browser sessions use HttpOnly, SameSite=Strict cookies; secure cookies are used when requests reach the app over HTTPS. Access requires the manager key or a valid session. Worker credentials cannot administer the library.

Claims serialize through `BEGIN IMMEDIATE`. A worker gets one active job and a random lease. Heartbeats renew it; cancellation/revocation clears it. Late or wrong-worker source/result requests are rejected. Expired jobs become failed for explicit review/retry, avoiding automatic duplicate processing. Pending jobs wait for compatible engines/codecs and optional worker targeting.

## Media preservation

The manager resolves paths below fixed library/output roots, rejects traversal and external symlinks, fingerprints each source and hashes it while queueing. The worker checks the download hash against that fingerprint. Recipes use allowlisted options rather than arbitrary FFmpeg arguments. Shell execution is never used for an engine command.

The worker preserves compatible audio, subtitle and attachment streams, chapters and metadata in MKV. This release processes the first non-cover-art video stream; additional video angles and data streams are not retained. Eight-bit SDR is the accepted source class; HDR/high-bit-depth inputs are rejected. Source originals remain read-only.

Before publishing, manager and worker check codec, dimensions, duration, stream counts and a real decode sample. Transfer SHA-256 verifies byte integrity. Publication links a hidden temporary file to a unique finished name inside a serialized job-state transaction. Cancelled uploads are discarded. Existing completed filenames are never replaced. Hard-crash leftovers remain temporary/unpublished and may need operator cleanup.

## Deployment boundaries

Default images build for Linux AMD64/ARM64. NVIDIA encoders need driver libraries and Container Toolkit. AI runtimes are optional, larger and hardware-specific. No proprietary models or DLSS runtimes ship in the default image. Linux GPU execution, native Windows adapters, Spark AI and external-drive hot-unplug require actual device acceptance; tests on a CPU Mac/container do not establish those capabilities.

## Integration direction

The HTTP API and versioned recipe schema are independent of the UI. Future Popcorn family tools can submit jobs and observe results using authenticated endpoints. Automatic folder policies, resumable transfers, verified HDR/color pipelines, schedules, multi-GPU concurrency, metrics and a first-party Linux DLSS renderer remain future extensions.
