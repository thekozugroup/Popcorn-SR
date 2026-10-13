import math
from fractions import Fraction

import numpy as np
import pytest

from popcorn_sr.frame_generation import FPS, cadence, nearest_frames, plan_factors
from popcorn_sr.video_pipe import encoded_video, encoding_options


def test_native_and_cascade_plans_cover_the_actual_target_without_fallback():
    assert plan_factors(FPS["23.976"], FPS["59.94"], 6, "native") == (3,)
    assert plan_factors(FPS["23.976"], FPS["480"], 6) == (6, 4)
    assert plan_factors(FPS["23.976"], FPS["480"], 6, "cascade") == (2,) * 5
    with pytest.raises(ValueError, match="native DLSSG limit"):
        plan_factors(FPS["23.976"], FPS["480"], 6, "native")
    with pytest.raises(ValueError, match="above"):
        plan_factors(FPS["60"], FPS["59.94"], 6)
    for source in (Fraction(12), FPS["23.976"], FPS["59.94"], FPS["119.88"]):
        for target in FPS.values():
            if target > source:
                for mode in ("auto", "cascade"):
                    factors = plan_factors(source, target, 6, mode)
                    assert all(2 <= factor <= 6 for factor in factors)
                    assert source * math.prod(factors) >= target


def test_cadence_uses_only_existing_frames_and_exact_ticks_with_a_short_final_span():
    # Irregular SDK positions need selection, not another interpolation filter.
    frames = [(Fraction(0), "a"), (Fraction(1, 40), "b"), (Fraction(7, 100), "c")]
    end = Fraction(81, 1000)
    result = list(nearest_frames(iter(frames), Fraction(60), end))
    assert [time for time, _, _ in result] == [Fraction(index, 60) for index in range(5)]
    assert [rgb for _, _, rgb in result] == ["a", "b", "b", "c", "c"]
    assert sum(duration for _, duration, _ in result) == end
    assert result[-1][1] < Fraction(1, 60)
    with pytest.raises(ValueError, match="increase"):
        list(nearest_frames([(Fraction(0), "a"), (Fraction(0), "b")], 60, end))


def test_lossless_rgb_pipe_preserves_submillisecond_pts_for_dense_intermediates(tmp_path):
    import av

    source, output = tmp_path / "dense.nut", tmp_path / "cadence.nut"
    rate, clock = Fraction(600), Fraction(1, 600)
    rng = np.random.default_rng(494)
    original = [rng.integers(0, 256, (16, 32, 3), dtype=np.uint8) for _ in range(16)]
    with encoded_video(source, 32, 16, rate, clock, encoding_options("ffv1", 20)) as (container, encoded):
        for index, rgb in enumerate(original):
            frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            frame.pts, frame.time_base = index, clock
            for packet in encoded.encode(frame):
                container.mux(packet)
    with av.open(str(source)) as container:
        frames = list(container.decode(video=0))
        assert len(frames) == len(original)
        for index, (frame, rgb) in enumerate(zip(frames, original, strict=True)):
            assert Fraction(frame.pts) * frame.time_base == index / rate
            assert np.array_equal(frame.to_ndarray(format="rgb24"), rgb)
    count = cadence(source, output, Fraction(480), Fraction(16, 600), "ffv1", 20)
    assert count == 13
    with av.open(str(output)) as container:
        frames = list(container.decode(video=0))
        assert len(frames) == 13
        for index, frame in enumerate(frames):
            assert Fraction(frame.pts) * frame.time_base == Fraction(index, 480)
            assert any(np.array_equal(frame.to_ndarray(format="rgb24"), rgb) for rgb in original)


@pytest.mark.parametrize("audio_codec", ["pcm_s16le", "aac"])
@pytest.mark.parametrize("generation", [False, True])
@pytest.mark.parametrize("rendered_offset", [False, True])
def test_final_interval_and_preserved_media_keep_original_synchronization(tmp_path, audio_codec, generation, rendered_offset):
    import json
    import subprocess

    import av

    from popcorn_sr.media import preserved_command, probe, validate_output
    from popcorn_sr.models import Recipe

    source, rendered, returned = [tmp_path / name for name in ("source.mkv", "generated.mkv", "returned.mkv")]
    metadata = tmp_path / "chapters.txt"
    metadata.write_text(";FFMETADATA1\ntitle=Timing fixture\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\ntitle=Opening\n")
    attachment = tmp_path / "notes.txt"
    attachment.write_text("Preserve this attachment.")
    subtitle = tmp_path / "caption.srt"
    subtitle.write_text("1\n00:00:00,400 --> 00:00:00,700\nKeep this caption in sync.\n")
    subprocess.run([
        "ffmpeg", "-v", "error", "-itsoffset", "0.25", "-f", "lavfi", "-i", "testsrc2=size=32x16:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-f", "ffmetadata", "-i", str(metadata),
        "-i", str(subtitle),
        "-map", "0:v", "-map", "1:a", "-map", "3:s", "-map_metadata", "2", "-map_chapters", "2", "-t", "1",
        "-c:v", "libx264", "-bf", "0", "-c:a", audio_codec, "-c:s", "srt", "-attach", str(attachment),
        "-metadata:s:t", "mimetype=text/plain", str(source),
    ], check=True)
    end, rate = Fraction(751, 1000), Fraction(60 if generation else 24)
    with encoded_video(rendered, 32, 16, rate, Fraction(1, 60000), ["-c:v", "libx264", "-bf", "0", "-pix_fmt", "yuv420p"], end_time=end) as (container, video):
        for index in range(math.ceil(end * rate)):
            frame = av.VideoFrame.from_ndarray(np.full((16, 32, 3), index, dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = int(index / rate * 60000), Fraction(1, 60000)
            for packet in video.encode(frame):
                container.mux(packet)
    assert abs(probe(rendered)["duration"] - float(end)) <= .001
    if rendered_offset:
        # Third-party exporters can retain a leading audio stream. Only their
        # video is used, and its measured offset must not be applied twice.
        offset_file = tmp_path / "offset-rendered.mkv"
        subprocess.run([
            "ffmpeg", "-v", "error", "-itsoffset", "0.125", "-i", str(rendered),
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "pcm_s16le", "-t", "1", str(offset_file),
        ], check=True)
        rendered = offset_file
    # CPU-rendered pictures exercise remux timing, not NVIDIA execution.
    recipe = Recipe(frame_generation=generation, scale=1, encoder="nvidia").model_dump()
    timing = {"source_video_duration": str(end)} if generation else None
    subprocess.run(preserved_command(rendered, source, returned, recipe, probe(source), timing), check=True)
    validate_output(returned, probe(source), recipe)

    def streams(path):
        return json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-show_chapters", "-show_packets",
            "-show_data_hash", "sha256", "-of", "json", str(path),
        ]))

    original, result = streams(source), streams(returned)
    original_video, original_audio = original["streams"][:2]
    result_video, result_audio = result["streams"][:2]
    assert abs((float(result_video["start_time"]) - float(result_audio["start_time"])) - (
        float(original_video["start_time"]) - float(original_audio["start_time"])
    )) <= .001
    assert [p["data_hash"] for p in original["packets"] if p["stream_index"] == 1] == [
        p["data_hash"] for p in result["packets"] if p["stream_index"] == 1
    ]
    assert result["streams"][3]["extradata_hash"] == original["streams"][3]["extradata_hash"]
    # AAC priming may start before zero. Remux can shift the whole timeline;
    # chapters and copied packets must retain their relationship to the picture.
    shift = Fraction(result_video["start_time"]) - Fraction(original_video["start_time"])
    assert len(result["chapters"]) == len(original["chapters"])
    for before, after in zip(original["chapters"], result["chapters"], strict=True):
        assert after["tags"] == before["tags"]
        for field in ("start_time", "end_time"):
            assert abs(Fraction(after[field]) - Fraction(before[field]) - shift) <= Fraction(1, 1000)
    before_audio = [p for p in original["packets"] if p["stream_index"] == 1]
    after_audio = [p for p in result["packets"] if p["stream_index"] == 1]
    for before, after in zip(before_audio, after_audio, strict=True):
        assert abs(Fraction(after["pts_time"]) - Fraction(before["pts_time"]) - shift) <= Fraction(1, 1000)
    before_subtitle = [p for p in original["packets"] if p["stream_index"] == 2]
    after_subtitle = [p for p in result["packets"] if p["stream_index"] == 2]
    assert len(before_subtitle) == len(after_subtitle) == 1
    assert before_subtitle[0]["data_hash"] == after_subtitle[0]["data_hash"]
    assert abs(Fraction(after_subtitle[0]["pts_time"]) - Fraction(before_subtitle[0]["pts_time"]) - shift) <= Fraction(1, 1000)
    assert result["format"]["tags"]["title"] == "Timing fixture"
    assert abs(float(result_video["tags"]["DURATION"].split(":")[-1]) - (
        float(end) + float(result_video["start_time"])
    )) <= .001
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(returned), "-f", "null", "-"], check=True)


def test_manager_and_claim_route_only_verified_frame_generation_settings(setup, auth):
    from popcorn_sr.dlss import compatible_recipe
    from popcorn_sr.models import Recipe
    from tests.conftest import pair_worker

    client, store, _, _ = setup
    caps = {"engines": ["resize"], "encoders": ["h264_nvidia"]}
    old, _ = pair_worker(client, caps)
    recipe = Recipe(frame_generation=True, scale=1, encoder="nvidia", frame_rate="60").model_dump()
    assert client.post("/api/jobs", json={"path": "sample.mkv", "recipe": recipe}).status_code == 400
    checked = caps | {"dlss_frame_generation": {
        "maximum_factor": 6, "settings": [["auto", "high"], ["native", "high"]], "upscalers": ["resize"],
    }}
    worker, _ = pair_worker(client, checked)
    assert not compatible_recipe(recipe | {"frame_generation_quality": "low"}, checked)
    assert not compatible_recipe(recipe | {"engine": "dlss-sr"}, checked)
    assert not compatible_recipe(recipe | {"frame_generation_mode": "native", "frame_rate": "480"}, checked, {"frame_rate": "24"})
    for invalid in [
        recipe | {"frame_rate": "23.976"}, recipe | {"encoder": "cpu"}, recipe | {"interpolate": True},
        recipe | {"frame_generation_mode": "native", "frame_rate": "480"},
    ]:
        assert client.post("/api/jobs", json={"path": "sample.mkv", "recipe": invalid}).status_code == 400
    queued = client.post("/api/jobs", json={"path": "sample.mkv", "recipe": recipe})
    assert queued.status_code == 200
    assert store.claim(store.worker(old["token"]), 60) is None
    assert store.claim(store.worker(worker["token"]), 60)["id"] == queued.json()["id"]


@pytest.mark.parametrize(('rate', 'end'), [(Fraction(60), Fraction(10001, 10000)), (Fraction(480), Fraction(1001, 8000))])
def test_submillisecond_final_frame_does_not_expand_to_a_nominal_period(tmp_path, rate, end):
    import av

    from popcorn_sr.media import probe

    path = tmp_path / 'short-tail.mkv'
    count = math.ceil(rate * end)
    clock = Fraction(1, math.lcm(rate.numerator, end.denominator))
    with encoded_video(path, 32, 16, rate, clock, ['-c:v', 'libx264', '-bf', '0', '-pix_fmt', 'yuv420p'], end_time=end) as (container, video):
        for index in range(count):
            frame = av.VideoFrame.from_ndarray(np.zeros((16, 32, 3), dtype=np.uint8), format='rgb24')
            frame.pts, frame.time_base = int(index / rate / clock), clock
            for packet in video.encode(frame):
                container.mux(packet)
    with av.open(str(path)) as result:
        assert len(list(result.decode(video=0))) == count
    assert abs(probe(path)['duration'] - float(end)) <= .0015


def test_fractional_codec_declarations_need_actual_packet_cadence(tmp_path):
    import av

    from popcorn_sr.media import probe, validate_output
    from popcorn_sr.models import Recipe

    rate, clock = FPS['59.94'], Fraction(1, 60000)
    for step, valid in [(1001, True), (2000, False)]:
        path = tmp_path / f'cadence-{step}.mkv'
        with encoded_video(path, 32, 16, rate, clock, [
            '-c:v', 'libx265', '-bf', '0', '-x265-params', 'pools=1:frame-threads=1:log-level=error', '-pix_fmt', 'yuv420p',
        ]) as (container, video):
            for index in range(30):
                frame = av.VideoFrame.from_ndarray(np.zeros((16, 32, 3), dtype=np.uint8), format='rgb24')
                frame.pts, frame.time_base = index * step, clock
                for packet in video.encode(frame):
                    container.mux(packet)
        info = probe(path)
        # Real HEVC/Matroska approximates the declaration while packet timing
        # distinguishes genuine 59.94 from deliberately mislabeled 30 fps.
        assert abs(Fraction(info['frame_rate']) - rate) < rate / 100_000
        recipe = Recipe(codec='hevc', encoder='nvidia', scale=1, frame_generation=True, frame_rate='59.94').model_dump()
        if valid:
            validate_output(path, info, recipe)
        else:
            with pytest.raises(ValueError, match='packet timing'):
                validate_output(path, info, recipe)
