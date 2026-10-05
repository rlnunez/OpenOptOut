#!/usr/bin/env python3
"""Start isolated scanner toolbox container and install schemathesis."""
import os
import subprocess
from pathlib import Path


def main() -> None:
    reports_dir = Path("dast-reports")
    private_dir = Path("dast-private")
    reports_dir.mkdir(parents=True, exist_ok=True)
    private_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.chmod(0o777)

    image_tag = "python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            "dast-tools",
            "-v",
            f"{os.getcwd()}:/work",
            "-w",
            "/work",
            image_tag,
            "sleep",
            "infinity",
        ],
        check=True,
    )

    schemathesis_version = os.environ.get("SCHEMATHESIS_VERSION", "")
    req = f"schemathesis=={schemathesis_version}" if schemathesis_version else "schemathesis"
    subprocess.run(
        ["docker", "exec", "dast-tools", "python", "-m", "pip", "install", "--quiet", req],
        check=True,
    )

    dast_net = os.environ.get("DAST_NET", "")
    if dast_net:
        subprocess.run(["docker", "network", "connect", dast_net, "dast-tools"], check=True)


if __name__ == "__main__":
    main()
