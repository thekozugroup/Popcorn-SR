"""DLSS recipe settings shared by the manager and optional native video worker."""

from fractions import Fraction

MODES = {
    "dlaa": (5, Fraction(1)),
    "quality": (2, Fraction(3, 2)),
    "balanced": (1, Fraction(50, 29)),
    "performance": (0, Fraction(2)),
    "ultra-performance": (3, Fraction(3)),
}
PRESETS = {"default": 0, "j": 10, "k": 11, "l": 12, "m": 13}


def mode_for_recipe(recipe):
    # Keep existing saved recipes/jobs compatible with their original output size.
    return recipe.get("dlss_mode") or {1: "dlaa", 2: "performance", 3: "ultra-performance"}[recipe["scale"]]


def scale_for_recipe(recipe):
    if recipe["engine"] == "dlss-sr":
        return MODES[mode_for_recipe(recipe)][1]
    return recipe["scale"]


def compatible_recipe(recipe, capabilities, source=None):
    if recipe["engine"] not in capabilities.get("engines", []):
        return False
    if f"{recipe['codec']}_{recipe['encoder']}" not in capabilities.get("encoders", []):
        return False
    if recipe.get("frame_generation"):
        from .frame_generation import FPS, plan_factors

        checked = capabilities.get("dlss_frame_generation", {})
        if recipe["encoder"] != "nvidia" or recipe["engine"] not in checked.get("upscalers", []) or [
            recipe.get("frame_generation_mode", "auto"), recipe.get("frame_generation_quality", "high"),
        ] not in checked.get("settings", []):
            return False
        if source is not None:
            try:
                plan_factors(
                    Fraction(source["frame_rate"]), FPS[recipe.get("frame_rate", "60")],
                    checked.get("maximum_factor", 0), recipe.get("frame_generation_mode", "auto"),
                )
            except (ValueError, ZeroDivisionError, KeyError, TypeError):
                return False
    if recipe["engine"] == "dlss-sr" and (
        recipe.get("dlss_mode") is not None or recipe.get("dlss_preset", "default") != "default"
        or recipe.get("temporal_quality", "high") != "high"
    ):
        checked = capabilities.get("dlss_sr", {})
        return (
            [mode_for_recipe(recipe), recipe.get("dlss_preset", "default")] in checked.get("settings", [])
            and recipe.get("temporal_quality", "high") in checked.get("temporal_qualities", [])
        )
    return True
