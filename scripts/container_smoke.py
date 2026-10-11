from __future__ import annotations

import argparse
import subprocess
from uuid import uuid4

from artifact_smoke import verify_api, wait_for_url


def verify_container(image: str) -> None:
    name = "duty-api-smoke-" + uuid4().hex[:12]
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "--no-healthcheck",
            "-p",
            "127.0.0.1:0:8000",
            "-e",
            "DUTY_API_AUTH_ENABLED=false",
            image,
            "/app/.venv/bin/duty-schedule-api",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        port = subprocess.run(
            ["docker", "port", name, "8000/tcp"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        verify_api(f"http://{port}")
    except Exception:
        subprocess.run(["docker", "logs", name], check=False, timeout=10)
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", name], check=False, capture_output=True, timeout=15)
    print("Container API generation and guarded exports passed without source mounts")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image")
    parser.add_argument("--ui-url")
    args = parser.parse_args()
    if args.image:
        verify_container(args.image)
    if args.ui_url:
        wait_for_url(args.ui_url + "/_stcore/health")
    if not args.image and not args.ui_url:
        parser.error("Provide --image or --ui-url")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
