# Popcorn SR

## Purpose
Turn a video library into better-looking, efficiently encoded copies using processing power on the same machine or another device. A NAS owns the library; a paired worker does the heavy work and returns the finished video.

## Users
Self-hosters with a NAS, NVIDIA desktop, or DGX Spark. They should not need to understand a distributed system to start a job.

## Design
Taste + Impeccable. Restrained Apple-like hierarchy, native system typography, zinc neutral surfaces, Tailwind blue-500 as the sole action/focus accent. Blue-500 uses dark text for accessible contrast. Tailwind emerald-500/amber-500/red-500 are limited to semantic status indicators; text uses accessible darker counterparts. One primary action per view. Flat sections, thin dividers, no decorative charts, no fake activity. 8px control radius, 16px major-panel radius. 44px touch targets. Light/dark via system preference, reduced-motion-safe transitions.

## Main workspace
Input on the left, output queue with status on the right, upscaling settings underneath. Stack those sections on small screens. No dashboard, sidebar, onboarding diagram or separate queue/library pages. Show method, output size and format; one primary Add to queue action. Put device selection, destination and optional processing controls under More options. Devices & storage is secondary setup, with a direct return to videos. Keep selections/settings when visiting setup.

Input rows show original picture dimensions and codec on the right; output rows show requested dimensions while pending and accepted result dimensions/codec when finished. No file-savings figures. Select page handles a large visible batch. Optional resolution rules map each input group to its own target, preserve cropped/portrait aspect ratio, keep unmatched sizes, and apply to both previews and full runs. Keep the default workspace compact until those rules are opened.

The header connection indicator is a compact Astryx badge with a semantic tinted background and dot, vertically aligned beside Devices & storage on desktop. A connected worker can still be running processing checks; its detailed readiness belongs in Devices & storage and controls remain gated.

When inputs are selected, show one large Original/Enhanced frame comparison between the input/queue and settings. A batch picker appears only for multiple inputs; a time picker selects the frame. Expand the comparison without adding navigation or a modal. Use actual processing, invalidate changed frame/settings, and make full continuation available after both images load. Keep audiovisual samples for motion/HDR review; still comparison is SDR-only.

## Family identity
Use Popcorn Batch's three-circle triangular mark. Batch colors the top circle blue-500; SR colors the lower-right circle teal-500 (#14b8a6). This is a brand detail; actions/focus remain blue-500. Neutral circles/tile invert with the theme. The favicon uses the fixed dark tile.

## Delivery scope
Available verified Linux DLSS Super Resolution and frame generation can ship without neural rendering. Neural rendering is deferred until compatible authorized SDK access exists; do not expose or substitute a pretend implementation. VSR/HDR remain gated optional integrations requiring genuine runtime checks. NAS/worker and single-device processing, storage controls and original preservation remain core.

## Honest boundaries
AI capabilities must pass a real startup smoke check. Ordinary resizing must be labeled as resizing. Experimental DLSS rendering may alter appearance; it is separately opt-in. Windows engine binaries are user-installed and never redistributed. HDR inputs fail closed until a preservation path is verified. No silent CPU fallback from an explicitly requested GPU job.
