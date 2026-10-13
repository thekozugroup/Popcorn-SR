"""10-bit HDR frame transport and validation; no SDR-to-HDR substitute."""

from .video_pipe import nvidia_options

# Packed RGB is full range; RGB itself has no YUV matrix. The encoder converts
# to limited-range BT.2020 non-constant-luminance YUV without reducing precision.
RGB10_COLOR = {"color_range": 2, "colorspace": 0, "color_trc": 16, "color_primaries": 9}
HDR10_SIGNALING = [
    "-vf", "scale=in_range=full:out_range=limited:out_color_matrix=bt2020,"
    "setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=limited",
    "-color_primaries", "bt2020", "-color_trc", "smpte2084",
    "-colorspace", "bt2020nc", "-color_range", "tv",
]


def hdr_encoding_options(codec, quality):
    if codec not in {"hevc", "av1"}:
        raise ValueError("RTX HDR requires H.265 or AV1 with 10-bit NVIDIA encoding.")
    options = nvidia_options(codec, quality)
    options[options.index("-pix_fmt") + 1] = "p010le"
    return options + ["-profile:v", "main10" if codec == "hevc" else "main"] + HDR10_SIGNALING


def packed_hdr_frame(pixels):
    """Unpack genuine RGB10A2 into exact planar ten-bit values for the pipe.

    R occupies the low ten bits, G the next ten, then B and two alpha bits.
    NUT cannot identify packed x2bgr10le reliably and silently labels it RGB555.
    Planar gbrp10le has a defined NUT tag, preserving all 1,024 channel levels.
    """
    import av
    import numpy as np

    if pixels.ndim != 2 or pixels.dtype != np.dtype("uint32"):
        raise ValueError("HDR output must contain packed uint32 RGB10A2 pixels.")
    height, width = pixels.shape
    if not width or not height:
        raise ValueError("HDR output is empty.")
    frame = av.VideoFrame(width, height, "gbrp10le")
    for plane, shift in zip(frame.planes, (10, 20, 0), strict=True):
        if plane.line_size < width * 2 or plane.line_size % 2:
            raise ValueError("HDR frame has an invalid planar row stride.")
        values = ((pixels >> shift) & 1023).astype("<u2")
        storage = np.zeros((height, plane.line_size // 2), dtype="<u2")
        storage[:, :width] = values
        plane.update(storage.tobytes())
    for field, value in RGB10_COLOR.items():
        setattr(frame, field, value)
    return frame


def validate_hdr(info):
    """Reject wrong precision/signaling; this alone is not SDK conversion proof."""
    expected = {"bit_depth": 10, "color_primaries": "bt2020", "color_transfer": "smpte2084",
                "color_space": "bt2020nc", "color_range": "tv"}
    if info.get("codec") not in {"hevc", "av1"} or any(info.get(key) != value for key, value in expected.items()):
        raise ValueError("HDR output must be 10-bit H.265/AV1 with BT.2020, PQ and limited-range signaling.")
