#!/usr/bin/env python3
"""Run Popcorn SR's verification on this machine, without GitHub Actions."""

import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software-only", action="store_true",
                        help="Omit Docker build/roundtrip checks; this is partial verification.")
    parser.add_argument("--include-ai", action="store_true",
                        help="Also build the larger CUDA AI image. This is not a GPU render test.")
    parser.add_argument("--report", type=Path, help="New JSON receipt path under evidence/.")
    args = parser.parse_args()
    if args.software_only and args.include_ai:
        parser.error("--include-ai requires Docker checks.")
    repo = Path(__file__).resolve().parents[1]
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    receipt = (repo / (args.report or Path("evidence") / f"local-verification-{stamp}.json")).resolve()
    if not receipt.is_relative_to(repo / "evidence"):
        parser.error("Receipts must stay under the gitignored evidence/ directory.")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Reserve a new receipt. A failed rerun must not overwrite earlier proof.
    with receipt.open("x"):
        pass
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).splitlines()
    image = "popcorn-sr:local-" + stamp.lower()
    commands = [
        ("Locked dependencies", ["uv", "sync", "--frozen", "--extra", "dev", "--reinstall-package", "popcorn-sr"]),
        ("Python lint", ["uv", "run", "ruff", "check", "."]),
        ("Compose layouts", ["uv", "run", "python", "scripts/check-compose.py"]),
        ("Native source", ["uv", "run", "python", "scripts/check-native-source.py", "--download-headers"]),
        ("Python media and API tests", ["uv", "run", "pytest", "-q"]),
        ("Locked UI dependencies", ["npm", "ci", "--ignore-scripts"]),
        ("Production UI", ["npm", "run", "build"]),
        ("UI dependency audit", ["npm", "audit", "--audit-level=high"]),
        ("Browser installation", ["npx", "playwright", "install", "chromium"]),
        ("Browser workflows", ["npm", "run", "test:browser"]),
    ]
    if not args.software_only:
        label = "org.opencontainers.image.revision=" + commit
        commands += [
            ("Manager image", ["docker", "build", "--label", label, "-t", image, "."]),
            ("Paired Docker video delivery", ["uv", "run", "python", "scripts/docker-smoke.py",
                                             "--image", image, "--report", str(receipt.with_suffix(".docker.json"))]),
            ("Compose restart and storage recovery", ["uv", "run", "python", "scripts/docker-lifecycle.py",
                                                      "--image", image, "--report", str(receipt.with_suffix(".lifecycle.json"))]),
            ("NGX image", ["docker", "build", "--label", label, "-f", "Dockerfile.ngx", "-t", image + "-ngx", "."]),
            ("Paired NGX Docker delivery", ["uv", "run", "python", "scripts/docker-smoke.py",
                                          "--image", image, "--worker-image", image + "-ngx",
                                          "--report", str(receipt.with_suffix(".ngx-docker.json"))]),
        ]
        if args.include_ai:
            commands.append(("AI image", ["docker", "build", "--label", label,
                                           "-f", "Dockerfile.ai", "-t", image + "-ai", "."]))
    report = {"source_commit": commit, "checkout_changes": dirty, "status": "running",
              "docker_checks": not args.software_only, "ai_build": args.include_ai,
              "gpu_verified": False, "image": image if not args.software_only else None, "steps": []}
    try:
        for name, command in commands:
            print(f"\n{name}", flush=True)
            step = {"name": name, "command": command}
            report["steps"].append(step)
            start = time.monotonic()
            try:
                subprocess.run(command, cwd=repo, check=True)
            except BaseException:
                step["status"] = "failed"
                raise
            else:
                step["status"] = "passed"
            finally:
                step["seconds"] = round(time.monotonic() - start, 2)
        report["status"] = "passed"
        print(f"\n{'Software-only' if args.software_only else 'Local'} verification passed: {receipt}")
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        receipt.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
