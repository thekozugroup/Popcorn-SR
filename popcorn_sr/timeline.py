"""Cancellable decoded-video inspection before lossless multi-stage processing."""

import argparse
from pathlib import Path

from .frame_generation import source_timeline
from .scratch import atomic_private_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    timing = source_timeline(args.input)
    atomic_private_json(args.report, {key: str(value) if key != "frames" else value for key, value in timing.items()})


if __name__ == "__main__":
    main()
