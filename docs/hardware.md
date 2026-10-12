# Networking and scratch drives

## Ethernet

Both devices must reach the manager's IP and port. A shared switch/router is the easiest arrangement. A direct Ethernet cable also works: configure an unused private subnet, for example NAS `192.168.50.1/24` and worker `192.168.50.2/24`, with no default gateway on those dedicated ports. Point the worker at `http://192.168.50.1:8787`. Avoid reusing a subnet assigned to another interface. Firewalls must allow worker-to-manager traffic; workers need no inbound listener.

| Link | Theoretical payload ceiling | Ideal 20 GB transfer, one way |
|---|---:|---:|
| 1 GbE | 125 MB/s | 160 seconds |
| 2.5 GbE | 312.5 MB/s | 64 seconds |
| 10 GbE | 1,250 MB/s | 16 seconds |

Actual throughput is lower because of protocol overhead, storage speed, CPU load and competing traffic. One job transfers the whole source and later its finished output. Upscaled output can be much larger. The GPU processes a local copy, so network throughput does not need to match every decoded video frame.

DGX Spark includes a [10 GbE RJ-45 port](https://docs.nvidia.com/dgx/dgx-spark/hardware.html). The slower NAS port, switch port or drive sets the practical ceiling. A USB-C-to-Ethernet adapter is useful when a device lacks a suitable network port; that still uses Ethernet, not a raw USB host-to-host connection.

## USB-C

The connector shape is not a networking protocol. Two ordinary host USB-C ports generally cannot form a data network through a passive cable. A specialized host-to-host bridge may expose a network interface if both operating systems support it. Thunderbolt networking also requires Thunderbolt-capable ports and compatible OS support; USB-C alone is insufficient. Spark's documented ports should not be treated as proof of Thunderbolt networking.

Use USB-C for the external Optane enclosure, and Ethernet for the processing link.

## Wireless

Wi-Fi works when both devices are on a network that permits peer communication. Guest/client isolation can block pairing. Effective speeds and dropouts vary with interference, distance and access-point load. You cannot promise interruption-free processing on every wireless network.

Popcorn SR verifies each transfer's checksum. Temporary outputs remain separate. A sustained manager disconnect expires the worker lease or stops processing; review and retry after reconnecting. Transfers restart from the beginning in 0.1; ranged resume is future work. Wired networking is preferable for high-bitrate libraries and predictable long runs.

## Optane scratch drive

Mount the enclosure on the processing host, create a scratch subfolder there and initialize it. Bind that exact directory to `/scratch`. Source copies, intermediate videos, AI caches, optional model checkpoint and outgoing copies live there. Keep originals on the read-only NAS library mount and completed copies on its separate output mount.

The worker reserves at least four times the source size plus 1 GiB before processing a job. Output-size estimates are conservative but cannot guarantee space for every upscale; use a larger drive for high-resolution/long media. Transfers continuously check space; failures preserve the original. NVENC streams frames rather than storing image sequences, reducing temporary writes.

Configure Linux systemd mount dependencies (`RequiresMountsFor`) or the host's equivalent. Compose uses `create_host_path: false`, and the worker requires a drive marker. This guards a missing path but is not a physical mount detector; do not initialize a placeholder directory while the drive is absent.

The application cannot prevent OS swap, Docker image layers, system logs, driver caches or enclosure firmware writes. Move/configure those separately for a whole-system endurance policy. Optane's endurance does not eliminate enclosure bandwidth, cooling, cable or power constraints.
