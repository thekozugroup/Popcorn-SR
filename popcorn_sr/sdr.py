"""Preserve SDR color through RGB processing without guessing missing labels."""

import json
import subprocess
from dataclasses import dataclass
from functools import cached_property

PROFILE_TAG = "popcorn_sdr_color"
MATRICES = {0: "gbr", 1: "bt709", 2: "unknown", 4: "fcc", 5: "bt470bg", 6: "smpte170m", 7: "smpte240m"}
PRIMARIES = {1: "bt709", 2: "unknown", 4: "bt470m", 5: "bt470bg", 6: "smpte170m", 7: "smpte240m",
             8: "film", 9: "bt2020", 10: "smpte428", 11: "smpte431", 12: "smpte432", 22: "ebu3213"}
TRANSFERS = {1: "bt709", 2: "unknown", 4: "gamma22", 5: "gamma28", 6: "smpte170m", 7: "smpte240m",
             8: "linear", 9: "log", 10: "log_sqrt", 11: "iec61966-2-4", 12: "bt1361e",
             13: "iec61966-2-1", 14: "bt2020-10", 15: "bt2020-12"}
RANGES = {0: "unknown", 1: "tv", 2: "pc"}
SCALE_MATRICES = {1: "bt709", 4: "fcc", 5: "bt601", 6: "bt601", 7: "smpte240m"}
FIELDS = {"colorspace": MATRICES, "color_range": RANGES, "color_trc": TRANSFERS, "color_primaries": PRIMARIES}
INFO_FIELDS = {"colorspace": "color_space", "color_range": "color_range",
               "color_trc": "color_transfer", "color_primaries": "color_primaries"}


@dataclass(frozen=True)
class SDRColor:
    colorspace: int = 2
    color_range: int = 0
    color_trc: int = 2
    color_primaries: int = 2

    def __post_init__(self):
        for field, values in FIELDS.items():
            value = getattr(self, field)
            if type(value) is not int or value not in values:
                raise ValueError("This SDR color profile is unsupported; refusing to change its colors.")

    @classmethod
    def from_info(cls, info):
        values = {}
        for field, names in FIELDS.items():
            label = info.get(INFO_FIELDS[field], "unknown")
            try:
                values[field] = next(value for value, name in names.items() if name == label)
            except StopIteration:
                raise ValueError("This SDR color profile is unsupported; refusing to change its colors.") from None
        return cls(**values)

    @classmethod
    def read(cls, path):
        # ffprobe sees codec/container signaling, including fields omitted by
        # some PyAV stream contexts. This reads headers, not a second decode.
        result = subprocess.run([
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ], capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(result.stdout)
        video = next(s for s in data["streams"] if s.get("codec_type") == "video"
                     and not s.get("disposition", {}).get("attached_pic"))
        tags = {k.lower(): v for k, v in data.get("format", {}).get("tags", {}).items()}
        if PROFILE_TAG in tags:
            # A profile describes the intended final YUV encoding, never the
            # current RGB pixels. Refuse a forged/malformed or misplaced tag.
            if video.get("pix_fmt") not in {"bgr0", "rgb24", "gbrp"} or len(tags[PROFILE_TAG]) > 256:
                raise ValueError("Invalid intermediate SDR color profile.")
            values = json.loads(tags[PROFILE_TAG])
            if not isinstance(values, dict) or set(values) != set(FIELDS):
                raise ValueError("Invalid intermediate SDR color profile.")
            return cls(**values)
        return cls.from_info(video)

    def serialized(self):
        return json.dumps({field: getattr(self, field) for field in FIELDS}, separators=(",", ":"))

    @cached_property
    def _reformatter(self):
        from av.video.reformatter import VideoReformatter

        return VideoReformatter()

    def rgb(self, frame):
        """Convert the actual decoded matrix/range; RGB intermediates stay RGB."""
        for field in ("color_trc", "color_primaries"):
            actual, intended = int(getattr(frame, field)), getattr(self, field)
            if actual not in FIELDS[field] or (actual != 2 and intended != 2 and actual != intended):
                raise ValueError("SDR color information changed during decoding.")
        if frame.format.is_rgb:
            return frame.to_ndarray(format="rgb24")
        actual_matrix, actual_range = int(frame.colorspace), int(frame.color_range)
        if actual_matrix not in MATRICES or actual_matrix == 0:
            raise ValueError("Decoded SDR color matrix is unsupported.")
        if self.colorspace not in {0, 2} and actual_matrix not in {2, self.colorspace}:
            raise ValueError("SDR color matrix changed during decoding.")
        if self.color_range and actual_range not in {0, self.color_range}:
            raise ValueError("SDR color range changed during decoding.")
        matrix = self.colorspace if self.colorspace not in {0, 2} else actual_matrix
        # PyAV's ITU601 enum is 5 (SWS); both 625/525 AVFrame matrices map to it.
        matrix = 5 if matrix in {5, 6} else matrix
        return self._reformatter.reformat(
            frame, format="rgb24", src_colorspace=matrix,
            src_color_range=self.color_range or actual_range, dst_color_range=2, threads=2,
        ).to_ndarray()

    def options(self, *, intermediate=False):
        if intermediate:
            # Actual RGB pixels use identity/full, retaining the source gamma
            # and primaries. NUT doesn't retain every codec color field; the
            # validated tag carries the final YUV profile between processes.
            params = f"range=full:colorspace=gbr:color_trc={TRANSFERS[self.color_trc]}:color_primaries={PRIMARIES[self.color_primaries]}"
            return ["-vf", "setparams=" + params, "-metadata", f"{PROFILE_TAG}={self.serialized()}",
                    "-colorspace", "0", "-color_range", "2", "-color_trc", str(self.color_trc),
                    "-color_primaries", str(self.color_primaries)]
        # Convert RGB pixels with the requested matrix before labeling them.
        # Missing labels remain unspecified; the historical 601/limited
        # conversion remains the fallback, never a newly invented BT.709 tag.
        # FFmpeg 7 uses the common scale-filter name bt601 for both matrices;
        # keep the distinct original 525/625 signaling in setparams/encoder.
        matrix = SCALE_MATRICES.get(self.colorspace, "bt601")
        range_name = "full" if self.color_range == 2 else "limited"
        labels = {"colorspace": MATRICES[self.colorspace] if self.colorspace != 0 else "unknown",
                  "range": RANGES[self.color_range], "color_trc": TRANSFERS[self.color_trc],
                  "color_primaries": PRIMARIES[self.color_primaries]}
        params = ":".join(f"{key}={value}" for key, value in labels.items())
        return ["-vf", f"scale=in_range=full:out_range={range_name}:out_color_matrix={matrix},setparams={params}",
                "-colorspace", str(self.colorspace if self.colorspace != 0 else 2), "-color_range", str(self.color_range),
                "-color_trc", str(self.color_trc), "-color_primaries", str(self.color_primaries),
                "-metadata", f"{PROFILE_TAG}="]


def validate_sdr(source, output):
    for field in INFO_FIELDS.values():
        value = source.get(field, "unknown")
        if value not in {"unknown", "gbr"} and output.get(field, "unknown") != value:
            raise ValueError("Output lost the source SDR color information. Original preserved; result rejected.")
