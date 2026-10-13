from fractions import Fraction

import pytest

from popcorn_sr.dlssg import graphics_scratch, intermediate_times, output_time_base


def test_generated_frame_timing_preserves_irregular_source_boundaries():
    # Intermediates sit within their source intervals; every source PTS remains
    # unchanged. Fractional cinema and irregular intervals stay rational.
    source = [Fraction(0), Fraction(1001, 24000), Fraction(1, 10), Fraction(13, 100)]
    for factor in (2, 3, 4, 8):
        output = [source[0]]
        for previous, current in zip(source, source[1:], strict=False):
            middle = intermediate_times(previous, current, factor)
            assert len(middle) == factor - 1
            assert all(previous < value < current for value in middle)
            assert middle[0] - previous == (current - previous) / factor
            output.extend((*middle, current))
        assert output[::factor] == source
        assert all(a < b for a, b in zip(output, output[1:], strict=False))
        assert output[-1] == source[-1]
    with pytest.raises(ValueError, match="timestamps"):
        intermediate_times(Fraction(1), Fraction(1), 2)
    with pytest.raises(ValueError, match="multiplier"):
        intermediate_times(0, 1, 1)


def test_output_clock_includes_rounded_container_ticks_and_cinema_periods():
    for rate in (Fraction(24), Fraction(24000, 1001)):
        for factor in (2, 3, 8):
            clock = output_time_base(Fraction(1, 1000), rate, factor)
            boundaries = [Fraction(1958, 1000), Fraction(1958, 1000) + 1 / rate]
            for timestamp in (*boundaries, *intermediate_times(*boundaries, factor)):
                assert (timestamp / clock).denominator == 1


def test_graphics_cache_cleanup_restores_existing_paths(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    monkeypatch.setenv("__GL_SHADER_DISK_CACHE_PATH", "/existing-shader-cache")
    monkeypatch.delenv("MESA_SHADER_CACHE_DIR", raising=False)
    with pytest.raises(RuntimeError):
        with graphics_scratch(tmp_path / "out.mkv") as scratch:
            owned = Path(scratch)
            assert owned.stat().st_mode & 0o777 == 0o700
            assert os.environ["__GL_SHADER_DISK_CACHE_PATH"] == scratch == os.environ["MESA_SHADER_CACHE_DIR"]
            (owned / "temporary-cache").write_bytes(b"test cache")
            raise RuntimeError("simulated SDK failure")
    assert not owned.exists()
    assert os.environ["__GL_SHADER_DISK_CACHE_PATH"] == "/existing-shader-cache"
    assert "MESA_SHADER_CACHE_DIR" not in os.environ
