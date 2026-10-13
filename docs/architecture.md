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

`POST /api/jobs/{id}/full` continues a completed preview using its saved recipe with `preview_seconds=0`. It verifies the source SHA-256 is unchanged and rechecks the selected worker/compatible engines and codecs. Incomplete previews, changed sources and incompatible workers fail with a clear recovery message.

Frame comparisons set `preview_frame_time` and `preview_seconds=5`. The worker accurately seeks into the verified source, makes a lossless video-only sample on its marked scratch drive, normalizes its picture clock and runs the selected enhancement/encoding pipeline. Both validators check the remaining duration, dimensions, codec and explicit zero auxiliary-stream contract. The preservation exemption applies only to these bounded still samples; full continuation clears the selected time and keeps all existing full-export checks. The first enhanced picture and the original at the same seek time are decoded through authenticated frame endpoints. Frames are PNGs with a maximum 1920-pixel display edge, not cached files or full-resolution image exports. The manager serializes frame decoding and returned-media validation, bounds FFmpeg threads, restricts file protocols and returns no-store images. Source-path containment and saved source size/mtime are rechecked; full continuation additionally rehashes the source.

The cancellable sampler makes two bounded seeks through the selected window: one measures its frame clocks/end, and one emits frames through the existing lossless pipe. It retains a declared nominal rate without duplicating pictures and preserves variable timestamps and a long final interval across FFmpeg versions. PyAV 17 and NumPy 2.3.3 are core worker dependencies, included in the base image as well as NVIDIA images; the manager does not import them for frame decoding. This adds image bytes without loading a GPU or model runtime on the NAS.

The browser keeps input/batch choices, frame time and the preview's settings. Changed selections invalidate the comparison, and a full continuation needs both displayed frames loaded. Completed samples reopen with their saved settings. Batch queueing is sequential: successful entries leave the selection, while remaining entries stay available if a later source fails. Native frame-generation pass progress is normalized across every inference pass and final cadence encoding, then mapped into the job's phase range so progress does not reset between passes.

## Media preservation

The manager resolves paths below fixed library/output roots, rejects traversal and external symlinks, fingerprints each source and hashes it while queueing. The worker checks the download hash against that fingerprint. Recipes use allowlisted options rather than arbitrary FFmpeg arguments. Shell execution is never used for an engine command.

The worker preserves compatible audio, subtitle and attachment streams, chapters and metadata in MKV. This release processes the first non-cover-art video stream; additional video angles and data streams are not retained. Eight-bit SDR is the accepted source class; HDR/high-bit-depth inputs are rejected. Source originals remain read-only.

Before publishing, manager and worker check codec, dimensions, duration, stream counts and a real decode sample. Transfer SHA-256 verifies byte integrity. Publication links a hidden temporary file to a unique finished name inside a serialized job-state transaction. Cancelled uploads are discarded. Existing completed filenames are never replaced. Hard-crash leftovers remain temporary/unpublished and may need operator cleanup.

The playback sample uses two decoder threads and one filter/output thread. FFmpeg's automatic thread count follows the host CPU inventory, which can exhaust a small NAS container's memory even when its CPU quota is low. These limits bound decoder buffers; they do not alter the exported video or remove the media-preservation checks. The Docker smoke test independently returns a generated 4K clip through a manager limited to 512 MiB and checks publication, audio, original/download hashes and absence of memory kills.

## Deployment boundaries

Default images build for Linux AMD64/ARM64. NVIDIA encoders need driver libraries and Container Toolkit. AI runtimes are optional, larger and hardware-specific. No proprietary models or DLSS runtimes ship in the default image. Linux GPU execution, native Windows adapters, Spark AI and external-drive hot-unplug require actual device acceptance; tests on a CPU Mac/container do not establish those capabilities.

## Integration direction

The HTTP API and versioned recipe schema are independent of the UI. Future Popcorn family tools can submit jobs and observe results using authenticated endpoints. Automatic folder policies, resumable transfers, verified HDR/color pipelines, schedules, multi-GPU concurrency, metrics and a first-party Linux DLSS renderer remain future extensions.

## Web interface

The official Astryx 0.6.8 components run on React 19. The custom theme extends Astryx Neutral with Tailwind zinc surfaces and blue-500 actions. System fonts need no download. The theme is compiled before Vite bundles the app; the NAS serves local assets through FastAPI. Both Docker and wheel builds include the generated static directory. Run `npm ci --ignore-scripts && npm run build` before building a wheel or running the manager from source.

The main workspace combines the input browser and output queue, with recipe controls below them. There is no navigation drawer or separate dashboard/library/queue. Official Astryx supplies keyboard-aware selectors, buttons, inputs, disclosures, notices, typography and progress. Setup has one Devices & storage entry. Recipe state survives polling and a visit to setup; selecting another input keeps the chosen settings. Capabilities still come from the manager's verified worker inventory. [Rust component assessment](rust-assessment.md).
