"""Per-source resolution rules, preserving aspect ratio and verified DLSS modes."""

import math
from fractions import Fraction

from .dlss import MODES

SIZES = {480: (854, 480), 720: (1280, 720), 1080: (1920, 1080),
         1440: (2560, 1440), 2160: (3840, 2160), 4320: (7680, 4320)}


def tier(width, height):
    """Use the enclosing video format, including cropped and portrait pictures."""
    long, short = sorted((width, height), reverse=True)
    return next((str(name) for name, (w, h) in SIZES.items() if long <= w + 8 and short <= h + 8), "other")


def target_dimensions(source, resolution, alignment=2):
    w, h = SIZES[resolution]
    if source["height"] > source["width"]:
        w, h = h, w
    factor = min(Fraction(w, source["width"]), Fraction(h, source["height"]))
    return tuple(max(alignment, math.floor(source[key] * factor / alignment) * alignment)
                 for key in ("width", "height"))


def resolve(recipe, source, workers):
    recipe = dict(recipe)
    rules = recipe.get("resolution_rules")
    if rules is not None:
        choice = rules.get(tier(source["width"], source["height"]), "keep")
        recipe["target_resolution"] = None if choice == "keep" else int(choice)
        if choice == "keep":
            recipe["scale"] = 1
            if recipe["engine"] == "dlss-sr":
                recipe["dlss_mode"] = "dlaa"
    target = recipe.get("target_resolution")
    if target is not None:
        width, height = target_dimensions(source, target, 8 if recipe["engine"] == "rtx-vsr" else 2)
        if width < source["width"] or height < source["height"]:
            raise ValueError("Resolution rules only upscale or keep source size. Choose a larger target.")
        if recipe["engine"] == "dlss-sr":
            factor = max(Fraction(width, source["width"]), Fraction(height, source["height"]))
            settings = {mode for worker in workers
                        if worker["capabilities"].get("dlss_sr", {}).get("resolution_targets")
                        and recipe.get("temporal_quality", "high") in worker["capabilities"]["dlss_sr"].get("temporal_qualities", [])
                        for mode, preset in worker["capabilities"]["dlss_sr"].get("settings", [])
                        if preset == recipe.get("dlss_preset", "default")}
            modes = sorted((mode for mode in settings if MODES[mode][1] >= factor), key=lambda mode: MODES[mode][1])
            if not modes:
                raise ValueError("No verified DLSS mode can reach this resolution. Choose a smaller target or another enhancement.")
            recipe["dlss_mode"] = modes[0]
    return recipe
