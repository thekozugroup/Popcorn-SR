# Resolution rules

Use one set of settings for a mixed library. Open **Resolution rules** beneath the input and output panes, enable **Set output by input resolution**, and choose a target for each input size. The same rule applies to the selected-frame preview and its full-video continuation.

| Input group | Starting target |
| --- | --- |
| 480p | 720p |
| 720p | 1080p |
| 1080p | 4K |
| 1440p | 4K |
| 4K | Keep resolution |
| 8K | Keep resolution |
| Other sizes | Keep resolution |

Targets are editable; these are starting choices, not a recommendation to process an entire library. **Keep resolution** still enhances/encodes the video at its original size. Rules do not downscale or replace originals. Turn the option off to use the existing fixed scale or DLSS mode.

The input list shows the actual picture dimensions and source codec. The output queue shows the requested dimensions with **Target** while pending, then the actual dimensions and codec of the accepted result. It shows no file-savings estimate. Details retain the source dimensions for comparison.

Pictures keep their aspect ratio. For example, 1280×720 becomes 1920×1080, 1920×1080 becomes 3840×2160, and a cropped 1920×800 picture becomes 3840×1600 when targeting 4K. Portrait video uses the corresponding portrait bounds. Inputs are grouped by the smallest enclosing standard frame size, allowing eight pixels of rounding; this recognizes common cropped movie frames without stretching them. Unmatched groups keep their size. Exact output dimensions can differ from the nominal resolution because of aspect ratio and codec alignment.

An updated worker must advertise verified rule support. Conventional resizing and Real-ESRGAN can fit a target directly. RTX Video requires verified custom-size support. Native DLSS selects the smallest verified mode that reaches the target, then reduces its enhanced picture to the final bounds when necessary. For example, 720p→1080p uses Quality, while 1080p→4K uses Performance. The final fit never enlarges DLSS output. A target beyond the worker's verified modes, an unavailable preset, or an oversized result is rejected with a reason; no silent change to another enhancement occurs.

Frame times refer to the first video picture. Audio that begins earlier does not shorten a selected-frame sample. Full exports preserve the original audio and picture offsets. Still comparisons remain SDR-only; HDR/high-bit-depth input protections are unchanged.

Resolution rules require manager and worker version 0.4.1 or later. Available enhancement settings still depend on genuine runtime checks. Review the representative preview on your intended player before processing a large batch.
