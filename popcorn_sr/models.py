from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Engine = Literal["resize", "realesrgan", "rtx-vsr", "dlss-sr", "dlss5"]
Codec = Literal["h264", "hevc", "av1"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Recipe(StrictModel):
    engine: Engine = "resize"
    codec: Codec = "h264"
    encoder: Literal["cpu", "nvidia"] = "cpu"
    scale: Literal[1, 2, 3, 4] = 2
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
    preview_seconds: Literal[0, 5, 10, 30] = 0
    output_directory: str = Field(default="enhanced", min_length=1, max_length=200)


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
