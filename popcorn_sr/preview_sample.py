"""Cancellable, bounded lossless preview sampling with original picture clocks."""

import argparse
from fractions import Fraction
from pathlib import Path

from .sdr import SDRColor
from .video_pipe import encoded_video, encoding_options


def pictures(path, start, seconds, clock="video"):
    import av

    with av.open(str(path), options={"protocol_whitelist": "file,pipe"}) as source:
        video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
        if not video.average_rate or not video.time_base or source.start_time is None:
            raise ValueError("Preview source timing is unavailable; refusing to guess.")
        video.codec_context.thread_count = 2
        video.thread_type = "SLICE"
        if clock == "video" and video.start_time is None:
            raise ValueError("Preview picture start time is unavailable; refusing to guess.")
        origin = Fraction(video.start_time) * video.time_base if clock == "video" else Fraction(source.start_time, av.time_base)
        target = origin + start
        if target:
            source.seek(int(target / video.time_base), stream=video, backward=True)
        previous = None
        for frame in source.decode(video):
            if frame.pts is None or frame.time_base is None:
                raise ValueError("Preview picture timestamp is missing.")
            timestamp = Fraction(frame.pts) * frame.time_base
            if timestamp < target:
                continue
            if timestamp >= target + seconds:
                break
            if previous is not None and timestamp <= previous:
                raise ValueError("Preview picture timestamps must increase.")
            duration = Fraction(frame.duration) * frame.time_base if frame.duration and frame.duration > 0 else 1 / video.average_rate
            previous = timestamp
            yield frame, timestamp, min(timestamp + duration, target + seconds), video.average_rate, video.time_base


def sample(input_path, output_path, start, seconds, clock="video"):
    import av

    start, seconds = Fraction(start), Fraction(seconds)
    if start < 0 or not 0 < seconds <= 30 or clock not in {"video", "container"}:
        raise ValueError("Preview bounds are invalid.")
    color = SDRColor.read(input_path)
    first, last, end, count = None, None, None, 0
    # Inspect only the selected window without retaining picture buffers.
    # The second seek emits frames; the measured final interval lets the
    # lossless pipe keep VFR end timing as well as its declared rate.
    for frame, timestamp, picture_end, _rate, _clock in pictures(input_path, start, seconds, clock):
        first = timestamp if first is None else first
        last, end, count = timestamp, picture_end, count + 1
        width, height = frame.width, frame.height
        rate, time_base = _rate, _clock
    if not count:
        raise ValueError("No frame exists at this time. Choose an earlier time.")
    with encoded_video(output_path, width, height, rate, time_base, [*encoding_options("ffv1", 23), "-threads", "2"],
                       end_time=end - first, final_frame_time=last - first, sdr_color=color) as (output, stream):
        for frame, timestamp, _, _, _ in pictures(input_path, start, seconds, clock):
            picture = av.VideoFrame.from_ndarray(color.rgb(frame), format="rgb24")
            picture.pts, picture.time_base = int((timestamp - first) / time_base), time_base
            for packet in stream.encode(picture):
                output.mux(packet)
            print(f"out_time_us={int((timestamp-first)*1_000_000)}", flush=True)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="0")
    parser.add_argument("--seconds", required=True)
    parser.add_argument("--clock", choices=("video", "container"), default="video")
    args = parser.parse_args()
    sample(args.input, args.output, args.start, args.seconds, args.clock)


if __name__ == "__main__":
    main()
