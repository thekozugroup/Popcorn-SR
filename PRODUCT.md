# Popcorn SR

## Purpose
Turn a video library into better-looking, efficiently encoded copies using processing power on the same machine or another device. A NAS owns the library; a paired worker does the heavy work and returns the finished video.

## Users
Self-hosters with a NAS, NVIDIA desktop, or DGX Spark. They should not need to understand a distributed system to start a job.

## Design
Taste + Impeccable. Restrained Apple-like hierarchy, native system typography, zinc neutral surfaces, Tailwind blue-500 as the sole action/focus accent. Blue-500 uses dark text for accessible contrast. Tailwind emerald-500/amber-500/red-500 are limited to semantic status indicators; text uses accessible darker counterparts. One primary action per view. Flat sections, thin dividers, no decorative charts, no fake activity. 8px control radius, 16px major-panel radius. 44px touch targets. Light/dark via system preference, reduced-motion-safe transitions.

## Journey
1. Connect library: mount the original read-only and choose a relative destination below the output mount.
2. Connect processing: short-lived one-use pairing code; show actual codecs, enhancements and scratch storage.
3. Review and run: select video, engine, size, codec and optional cleanup. Preview a short clip first. Preserve originals, audio, subtitles, metadata and chapters.

## Honest boundaries
AI capabilities must pass a real startup smoke check. Ordinary resizing must be labeled as resizing. Experimental DLSS rendering may alter appearance; it is separately opt-in. Windows engine binaries are user-installed and never redistributed. HDR inputs fail closed until a preservation path is verified. No silent CPU fallback from an explicitly requested GPU job.
