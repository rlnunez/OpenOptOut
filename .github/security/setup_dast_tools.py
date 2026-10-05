#!/usr/bin/env python3
"""Start isolated scanner toolbox container and install schemathesis."""
import os
import re
import shlex
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

    raw_ver = os.environ.get("SCHEMATHESIS_VERSION", "4.28.0").strip()
    ver = raw_ver if re.match(r"^[0-9A-Za-z_.\-]+$", raw_ver) else "4.28.0"
    req = shlex.quote(f"schemathesis=={ver}")

    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(
        ["docker", "exec", "dast-tools", "python", "-m", "pip", "install", "--quiet", req],
        check=True,
    )

    raw_net = os.environ.get("DAST_NET", "oodast_dast").strip()
    net = raw_net if re.match(r"^[0-9A-Za-z_.\-]+$", raw_net) else "oodast_dast"
    # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
    subprocess.run(["docker", "network", "connect", shlex.quote(net), "dast-tools"], check=True)


if __name__ == "__main__":
    main()
