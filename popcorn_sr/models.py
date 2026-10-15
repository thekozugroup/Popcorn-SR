from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Engine = Literal["resize", "realesrgan", "flashvsr", "rtx-vsr", "dlss-sr", "dlss5"]
Codec = Literal["h264", "hevc", "av1"]
Resolution = Literal[480, 720, 1080, 1440, 2160, 4320]
InputResolution = Literal["480", "720", "1080", "1440", "2160", "4320", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Recipe(StrictModel):
    engine: Engine = "resize"
    codec: Codec = "h264"
    encoder: Literal["cpu", "nvidia"] = "cpu"
    scale: Literal[1, 2, 3, 4] = 2
    target_resolution: Resolution | None = None
    resolution_rules: dict[InputResolution, Literal["keep", "480", "720", "1080", "1440", "2160", "4320"]] | None = None
    vsr_quality: Literal[1, 2, 3, 4] | None = None
    vsr_strength: float | None = Field(default=None, ge=0, le=1)
    output_width: int | None = Field(default=None, ge=64, le=7680)
    output_height: int | None = Field(default=None, ge=64, le=7680)
    dlss_mode: Literal["dlaa", "quality", "balanced", "performance", "ultra-performance"] | None = None
    dlss_preset: Literal["default", "j", "k", "l", "m"] = "default"
    temporal_quality: Literal["low", "medium", "high"] = "high"
    quality: int = Field(default=23, ge=16, le=32)
    denoise: bool = False
    deinterlace: bool = False
    sharpen: bool = False
    interpolate: bool = False
    frame_generation: bool = False
    frame_rate: Literal[
        "23.976", "25", "29.97", "30", "50", "59.94", "60", "90", "119.88", "120",
        "144", "165", "180", "240", "360", "480",
    ] = "60"
    frame_generation_mode: Literal["auto", "native", "cascade"] = "auto"
    frame_generation_quality: Literal["low", "medium", "high"] = "high"
    hdr: bool = False
    hdr_contrast: int = Field(default=100, ge=0, le=200)
    hdr_saturation: int = Field(default=100, ge=0, le=200)
    hdr_middle_gray: int = Field(default=50, ge=10, le=100)
    hdr_luminance: int = Field(default=650, ge=400, le=2000)
    hdr_debanding: bool = True
    preview_seconds: Literal[0, 5, 10, 30] = 0
    preview_frame_time: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_directory: str = Field(default="enhanced", min_length=1, max_length=200)

    @model_validator(mode="after")
    def vsr_controls(self):
        if (self.target_resolution is not None or self.resolution_rules is not None) and self.engine == "dlss5":
            raise ValueError("Neural rendering currently keeps source resolution.")
        if (self.target_resolution is not None or self.resolution_rules is not None) and self.output_width is not None:
            raise ValueError("Choose resolution rules or custom dimensions, not both.")
        if self.resolution_rules is not None:
            for original, output in self.resolution_rules.items():
                if output != "keep" and (original == "other" or int(output) < int(original)):
                    raise ValueError("Resolution rules only upscale or keep source size. Unmatched resolutions keep source size.")
        if self.preview_frame_time is not None and self.preview_seconds != 5:
            raise ValueError("Frame comparisons require a five-second preview sample.")
        controls = (self.vsr_quality, self.vsr_strength, self.output_width, self.output_height)
        if any(value is not None for value in controls) and self.engine != "rtx-vsr":
            raise ValueError("RTX Video settings require the RTX Video Super Resolution engine.")
        if (self.output_width is None) != (self.output_height is None):
            raise ValueError("Enter both output width and height.")
        if self.output_width is not None and (self.output_width % 8 or self.output_height % 8):
            raise ValueError("RTX Video output dimensions must be multiples of 8 pixels.")
        return self


class JobCreate(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    recipe: Recipe
    worker_id: str | None = None


class PairRequest(StrictModel):
    code: str = Field(min_length=16, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    capabilities: dict
    scratch: dict


class Heartbeat(StrictModel):
    lease: str
    progress: float = Field(default=0, ge=0, le=100)
    stage: str = Field(default="Processing", max_length=80)


class Failure(StrictModel):
    lease: str
    error: str = Field(min_length=1, max_length=2000)
