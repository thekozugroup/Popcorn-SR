#!/usr/bin/env python3
"""Build, reload and exercise public Docker release kits without GitHub Actions."""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(args, cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def loader(version, architecture, commit, packages):
    """No host paths, services, credentials, network or running containers are changed."""
    lines = [
        "#!/bin/sh", "set -eu", 'cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"',
        'case "$(uname -m)" in x86_64|amd64) host=amd64;; aarch64|arm64) host=arm64;; *) echo "Unsupported host architecture." >&2; exit 1;; esac',
        f'[ "$host" = "{architecture}" ] || {{ echo "This kit is for {architecture}. Download the kit matching this host." >&2; exit 1; }}',
        'role=${1:-manager}',
        'case "$role" in manager|ngx|all) ;; *) echo "Usage: ./load.sh [manager|ngx|all]" >&2; exit 1;; esac',
        'if command -v sha256sum >/dev/null 2>&1; then sha256sum --check --strict SHA256SUMS; else shasum -a 256 --check SHA256SUMS; fi',
    ]
    for name, package in packages.items():
        image = package["image"]
        layers = " ".join(package["rootfs_layers"])
        lines += [
            f'if [ "$role" = "{name}" ] || [ "$role" = "all" ]; then',
            f'  if docker image inspect "{image}" >/dev/null 2>&1; then',
            f'    current=$(docker image inspect --format \'{{{{index .Config.Labels "org.opencontainers.image.revision"}}}}\' "{image}")',
            f'    [ "$current" = "{commit}" ] || {{ echo "Refusing to replace an existing different {image} image." >&2; exit 1; }}',
            "  else",
            f'    docker load --input "{name}/image.tar.gz"',
            "  fi",
            f'  actual=$(docker image inspect --format \'{{{{join .RootFS.Layers " "}}}}\' "{image}")',
            f'  [ "$actual" = "{layers}" ] || {{ echo "Loaded image filesystem does not match the verified kit." >&2; exit 1; }}',
            f'  echo "Loaded {image}."',
            "fi",
        ]
    lines += [f'echo "Popcorn SR {version} images are loaded. Copy images.env values into your private .env, then follow README.txt."']
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory under evidence/.")
    parser.add_argument("--architectures", nargs="+", choices=["arm64", "amd64"], default=["arm64", "amd64"])
    parser.add_argument("--include-ai", action="store_true", help="Also build/import-check AI images; these are not bundled in the kit.")
    args = parser.parse_args()
    output = (REPO / args.output).resolve()
    if not output.is_relative_to(REPO / "evidence"):
        parser.error("Release artifacts must stay under evidence/.")
    if len(set(args.architectures)) != len(args.architectures):
        parser.error("Choose each architecture only once.")
    if run("git", "status", "--porcelain"):
        raise ValueError("Commit the intended release source before packaging.")
    output.mkdir(parents=True, exist_ok=False)
    commit = run("git", "rev-parse", "HEAD")
    version = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    if not all(part.isdigit() for part in version.split(".")) or len(version.split(".")) != 3:
        raise ValueError("Release kits require a numeric major.minor.patch version.")
    report = {"source_commit": commit, "version": version, "status": "running", "gpu_verified": False,
              "created_at": datetime.datetime.now(datetime.UTC).isoformat(), "platforms": {}}
    report_path = output / "verification.json"

    def save():
        report_path.write_text(json.dumps(report, indent=2) + "\n")

    save()
    try:
        for architecture in args.architectures:
            print(f"Building and verifying Linux {architecture} release kit.", flush=True)
            kit = output / f"popcorn-sr-{version}-linux-{architecture}"
            kit.mkdir()
            packages = {}
            for name, dockerfile, repository in (("manager", "Dockerfile", "popcorn-sr"),
                                                ("ngx", "Dockerfile.ngx", "popcorn-sr-ngx")):
                image = f"{repository}:{version}-{architecture}"
                existing = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
                if existing.returncode == 0:
                    raise ValueError(f"Choose an isolated builder: release image {image} already exists.")
                with (output / f"build-{name}-{architecture}.log").open("w") as log:
                    subprocess.run(["docker", "buildx", "build", "--platform", f"linux/{architecture}",
                                    "--load", "--label", f"org.opencontainers.image.revision={commit}",
                                    "--label", f"org.opencontainers.image.version={version}", "-f", dockerfile,
                                    "-t", image, "."], cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
                run("python", "scripts/export-device-package.py", "--image", image,
                    "--architecture", architecture, "--output", str(kit / name))
                packages[name] = json.loads((kit / name / "package.json").read_text())
            (kit / "load.sh").write_text(loader(version, architecture, commit, packages))
            (kit / "load.sh").chmod(0o755)
            (kit / "images.env").write_text(
                f"POPCORN_IMAGE={packages['manager']['image']}\nPOPCORN_NGX_IMAGE={packages['ngx']['image']}\n")
            for name in ("compose.yaml", "compose.worker.yaml", "compose.single.yaml", "compose.nvidia.yaml",
                         "compose.ngx.yaml", "compose.updates.yaml", ".env.example", "LICENSE", "THIRD-PARTY-NOTICES.md"):
                shutil.copyfile(REPO / name, kit / name)
            (kit / "scripts").mkdir()
            shutil.copyfile(REPO / "scripts/update-worker.py", kit / "scripts/update-worker.py")
            shutil.copytree(REPO / "systemd", kit / "systemd")
            shutil.copytree(REPO / "unraid", kit / "unraid")
            shutil.copytree(REPO / "docs", kit / "docs")
            shutil.copytree(REPO / "native", kit / "native")
            (kit / "README.txt").write_text(
                f"Popcorn SR {version} preview — Linux {architecture}\nSource: {commit}\n\n"
                "Run ./load.sh manager on the NAS, ./load.sh ngx on the NVIDIA worker, or ./load.sh all on one host.\n"
                "The loader verifies checksums and image identity. It only loads images; it does not create host folders, start services or edit your configuration.\n"
                "Copy .env.example to a private .env and set your actual library/output/state/scratch paths. Sign in with admin/admin and change the password.\n"
                "Append the two image selections from images.env to .env. Set PUID/PGID to the host user's IDs (99/100 on Unraid).\n"
                "Follow docs/deployment.md. With this kit use --no-build --pull never instead of --pull always.\n"
                "Manager: docker compose up -d --no-build --pull never manager\n"
                "Paired GPU worker: use compose.worker.yaml + compose.ngx.yaml; single host: compose.yaml + compose.single.yaml + compose.ngx.yaml.\n"
                "Initialize the mounted scratch subfolder before starting a worker, and create its one-use pairing code in the Web UI.\n"
                "Optional host-controlled worker updates: follow docs/updates.md using compose.updates.yaml, scripts/update-worker.py and systemd/.\n"
                "The NGX worker needs separately licensed NVIDIA runtimes/headers and the native bridges: native/README.md. No proprietary SDK or model is included.\n"
                "DLSS video adaptation is experimental. VSR/HDR/neural rendering require compatible additional runtimes and are gated. Preview your content before a batch.\n"
                "Image layers use the host's Docker data drive. Move that storage too if built-in drive endurance is a concern.\n")
            checksums = "".join(f"{digest(p)}  {p.relative_to(kit).as_posix()}\n"
                                for p in sorted(kit.rglob("*")) if p.is_file())
            (kit / "SHA256SUMS").write_text(checksums)
            archive = output / f"{kit.name}.tar.gz"
            with tarfile.open(archive, "w:gz", compresslevel=1) as stream:
                stream.add(kit, arcname=kit.name)
            archive_hash = digest(archive)
            (output / f"{archive.name}.sha256").write_text(f"{archive_hash}  {archive.name}\n")
            # Load the actual distributable into this isolated builder again.
            for package in packages.values():
                run("docker", "image", "rm", package["image"])
            with tempfile.TemporaryDirectory(prefix="release-import-", dir=output) as temporary:
                with tarfile.open(archive) as stream:
                    stream.extractall(temporary, filter="data")
                loaded = Path(temporary) / kit.name
                # An emulated AMD64 kit is imported directly; its host guard is
                # verified separately on native ARM64 and in guard regressions.
                if architecture == {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(os.uname().machine):
                    run("sh", str(loaded / "load.sh"), "all")
                else:
                    for package_name in packages:
                        run("docker", "load", "-i", str(loaded / package_name / "image.tar.gz"))
                for package in packages.values():
                    info = json.loads(run("docker", "image", "inspect", package["image"]))[0]
                    if (info["RootFS"]["Layers"] != package["rootfs_layers"] or
                            info["Config"]["Env"] != package["environment"] or info["Architecture"] != architecture or
                            info["Config"]["Labels"]["org.opencontainers.image.revision"] != commit):
                        raise ValueError("Imported image does not match the built package.")
                configuration = {
                    "POPCORN_IMAGE": packages["manager"]["image"], "POPCORN_NGX_IMAGE": packages["ngx"]["image"],
                    "POPCORN_MANAGER": "http://manager.example:8787", "POPCORN_NGX_BUNDLE": str(loaded / "runtime"),
                    "POPCORN_NGX_DRIVER": str(loaded / "driver.so"),
                    "UPDATE_CONTROL_PATH": str(loaded / "updates"),
                    **{key: str(loaded / key.lower()) for key in
                       ("STATE_PATH", "LIBRARY_PATH", "OUTPUT_PATH", "WORKER_STATE_PATH", "SCRATCH_PATH")},
                }
                settings = loaded / ".env"
                settings.write_text("".join(f"{k}={v}\n" for k, v in configuration.items()))
                environment = {k: v for k, v in os.environ.items() if not k.startswith("POPCORN_")}
                for files in (("compose.yaml",), ("compose.worker.yaml", "compose.ngx.yaml"),
                              ("compose.yaml", "compose.single.yaml", "compose.ngx.yaml"),
                              ("compose.worker.yaml", "compose.ngx.yaml", "compose.updates.yaml")):
                    command = ["docker", "compose", "--env-file", str(settings), "--project-directory", str(loaded)]
                    for name in files:
                        command += ["-f", str(loaded / name)]
                    rendered = subprocess.run(command + ["config", "--format", "json"], env=environment,
                                              capture_output=True, text=True, check=True)
                    services = json.loads(rendered.stdout)["services"]
                    for name, service in services.items():
                        expected = packages["manager" if name == "manager" else "ngx"]["image"]
                        if service["image"] != expected or not service["read_only"]:
                            raise ValueError("Release configuration selected the wrong or writable image.")
            smoke = output / f"delivery-{architecture}.json"
            with (output / f"delivery-{architecture}.log").open("w") as log:
                subprocess.run(["python", "scripts/docker-smoke.py", "--image", packages["manager"]["image"],
                                "--worker-image", packages["ngx"]["image"], "--report", str(smoke)],
                               cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
            report["platforms"][architecture] = {"archive": archive.name, "sha256": archive_hash,
                "bytes": archive.stat().st_size, "archive_import_identity_verified": True, "kit_configurations_verified": True,
                "delivery": json.loads(smoke.read_text()), "packages": packages}
            if args.include_ai:
                image = f"popcorn-sr-ai:{version}-{architecture}"
                with (output / f"build-ai-{architecture}.log").open("w") as log:
                    subprocess.run(["docker", "buildx", "build", "--platform", f"linux/{architecture}", "--load",
                                    "--label", f"org.opencontainers.image.revision={commit}", "--label",
                                    f"org.opencontainers.image.version={version}", "-f", "Dockerfile.ai", "-t", image, "."],
                                   cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)
                report["platforms"][architecture]["ai_image_build_and_imports_passed"] = True
            save()
        (output / "SHA256SUMS").write_text("".join(
            f"{v['sha256']}  {v['archive']}\n" for v in report["platforms"].values()))
        report["status"] = "passed"
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        save()
    print(f"Verified release kits: {output}")


if __name__ == "__main__":
    main()
