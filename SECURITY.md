# Security

Popcorn SR 0.1 is intended for a trusted home network. Put HTTPS or a VPN in front of the manager for access beyond that network. Keep the admin key, worker credentials and media out of bug reports.

Use **Report a vulnerability** in this repository's Security tab for private vulnerability reporting. Do not post exploit details or credentials in public issues.

The manager authenticates browser and worker requests separately. Pairing codes are short-lived and single-use. Source mounts should be read-only; outputs and scratch are separate. Worker engine command templates are trusted operator configuration and execute with the worker's permissions. Only install engines you trust.

Current automated acceptance covers CPU media processing and the API/browser/container workflow. GPU engines and physical storage/network behavior need device acceptance; startup smoke checks do not certify every input or runtime. Keep deployment dependencies and NVIDIA drivers updated, and preserve originals.
