from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path


def _hash(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _version(path: Path) -> str:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("Distribution metadata is missing or ambiguous")
            content = archive.read(names[0]).decode()
    else:
        with tarfile.open(path, "r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1
            ]
            if len(members) != 1:
                raise ValueError("Distribution metadata is missing or ambiguous")
            file = archive.extractfile(members[0])
            if file is None:
                raise ValueError("Distribution metadata is not a file")
            with file:
                content = file.read().decode()
    metadata = Parser().parsestr(content)
    if metadata.get("Name") != "duty-schedule":
        raise ValueError("Unexpected distribution name")
    return str(metadata.get("Version", ""))


def _validate_identity(sha: str, version: str) -> None:
    if re.fullmatch(r"[a-f0-9]{40}", sha) is None:
        raise ValueError("Invalid source SHA")
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][a-zA-Z0-9.]+)?", version) is None:
        raise ValueError("Invalid version")


def build_manifest(folder: Path, sha: str, version: str) -> None:
    _validate_identity(sha, version)
    wheels = sorted(folder.glob("*.whl"))
    sources = sorted(folder.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Release requires exactly one wheel and one source distribution")
    files = [*wheels, *sources]
    if any(_version(file) != version for file in files):
        raise ValueError("Distribution version does not match the verified version")
    records = [{"name": file.name, "sha256": _hash(file)} for file in files]
    (folder / "artifact-manifest.json").write_text(
        json.dumps({"source_sha": sha, "version": version, "files": records}, indent=2) + "\n"
    )
    (folder / "checksums.txt").write_text(
        "".join(f"{record['sha256']}  {record['name']}\n" for record in records)
    )


def verify_manifest(folder: Path, sha: str, version: str) -> list[Path]:
    _validate_identity(sha, version)
    manifest = json.loads((folder / "artifact-manifest.json").read_text())
    if manifest.get("source_sha") != sha:
        raise ValueError("Artifact source SHA does not match verified SHA")
    if manifest.get("version") != version:
        raise ValueError("Artifact version does not match verified version")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != 2:
        raise ValueError("Invalid distribution manifest")
    files: list[Path] = []
    for record in records:
        name = record.get("name")
        if not isinstance(name, str) or re.fullmatch(r"[a-zA-Z0-9_.+-]+", name) is None:
            raise ValueError("Invalid distribution filename")
        path = folder / name
        if path.is_symlink() or not path.is_file() or _hash(path) != record.get("sha256"):
            raise ValueError("Artifact checksum mismatch")
        if _version(path) != version:
            raise ValueError("Distribution version mismatch")
        files.append(path)
    actual = {*folder.glob("*.whl"), *folder.glob("*.tar.gz")}
    if len(actual) != 2 or set(files) != actual:
        raise ValueError("Artifact files do not match manifest")
    expected_checksums = "".join(f"{record['sha256']}  {record['name']}\n" for record in records)
    if (folder / "checksums.txt").read_text() != expected_checksums:
        raise ValueError("Artifact checksum file mismatch")
    return files


def verify_tag(existing_sha: str | None, verified_sha: str) -> None:
    if existing_sha is not None and existing_sha != verified_sha:
        raise ValueError("Existing tag refers to a different SHA; choose a new version")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("build", "verify", "tag"))
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--existing-sha")
    args = parser.parse_args()
    try:
        if args.operation == "build":
            build_manifest(args.dist, args.sha, args.version)
        elif args.operation == "verify":
            verify_manifest(args.dist, args.sha, args.version)
        else:
            _validate_identity(args.sha, args.version)
            verify_tag(args.existing_sha, args.sha)
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Verified {args.operation}: {args.sha} / {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
