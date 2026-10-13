import subprocess

import pytest

from popcorn_sr.media import inspect_source, preserved_command, probe, sha256, validate_output
from popcorn_sr.models import Recipe
from tests.conftest import pair_worker


def timing_fixture(tmp_path):
    source, rendered = tmp_path / "source.mkv", tmp_path / "rendered.mkv"
    chapters = tmp_path / "chapters.txt"
    chapters.write_text(
        ";FFMETADATA1\ntitle=Preserved title\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=3000\ntitle=Opening\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=4000\nEND=6000\ntitle=Closing\n"
        "[CHAPTER]\nTIMEBASE=1/1000\nSTART=5500\nEND=6000\ntitle=Beyond preview\n"
    )
    subprocess.run([
        "ffmpeg", "-v", "error", "-itsoffset", "0.25", "-f", "lavfi", "-i", "testsrc2=size=32x16:rate=24",
        "-f", "lavfi", "-i", "sine=sample_rate=48000", "-f", "ffmetadata", "-i", str(chapters),
        "-map", "0:v", "-map", "1:a", "-map_metadata", "2", "-map_chapters", "2", "-t", "6",
        "-c:v", "libx264", "-bf", "0", "-c:a", "aac", str(source),
    ], check=True)
    # Real CPU encoding simulates only the normalized timestamps of an
    # enhancement engine. It makes no NVIDIA inference claim.
    subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(source), "-map", "0:V:0", "-map_metadata", "-1",
        "-map_chapters", "-1", "-vf", "setpts=PTS-STARTPTS", "-c:v", "libx264", "-bf", "0", str(rendered),
    ], check=True)
    return source, rendered


@pytest.mark.parametrize("preview", [0, 5])
def test_real_enhancement_remux_preserves_audio_and_clips_preview_chapters(tmp_path, preview):
    source, rendered = timing_fixture(tmp_path)
    returned = tmp_path / "returned.mkv"
    recipe = Recipe(scale=1, preview_seconds=preview).model_dump()
    original = inspect_source(source)
    subprocess.run(preserved_command(rendered, source, returned, recipe, original), check=True)
    checked = validate_output(returned, original, recipe)
    assert len(checked["preservation"]["chapters"]) == (2 if preview else 3)
    assert sha256(source) == original["sha256"]


def test_nas_rejects_a_real_returned_file_with_shifted_picture(setup, auth, tmp_path):
    client, store, cfg, _ = setup
    source, rendered = timing_fixture(tmp_path)
    library_source = cfg.library / source.name
    library_source.write_bytes(source.read_bytes())
    original = inspect_source(library_source)
    recipe = Recipe(scale=1, preview_seconds=0).model_dump()
    credentials, _ = pair_worker(client)
    store.add_job(source.name, recipe, original)
    claim = store.claim(store.worker(credentials["token"]), 90)
    broken = tmp_path / "broken.mkv"
    # This is the former save step: stream counts, codec, duration and hashes
    # look valid, but the zero-based picture loses its original audio offset.
    subprocess.run([
        "ffmpeg", "-v", "error", "-i", str(rendered), "-i", str(source),
        "-map", "0:V:0", "-map", "1:a", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", str(broken),
    ], check=True)
    assert probe(broken)["audio_streams"] == original["audio_streams"]
    with pytest.raises(ValueError, match="timing"):
        validate_output(broken, original, recipe)
    response = client.put(
        f"/api/worker/jobs/{claim['id']}/result", content=broken.read_bytes(), headers={
            "Authorization": f"Bearer {credentials['token']}", "X-Job-Lease": claim["lease"],
            "X-Output-SHA256": sha256(broken),
        },
    )
    assert response.status_code == 400 and "timing" in response.json()["detail"]
    assert not list(cfg.output.rglob("*.mkv"))
    assert store.job(claim["id"])["status"] == "running"
    assert sha256(library_source) == original["sha256"]
