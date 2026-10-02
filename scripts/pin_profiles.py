"""Deployment-only daemon query: capture built profile digests without exposing credentials."""

import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--context", help="Optional Docker context; otherwise use the current context")
args = parser.parse_args()
docker = ["docker", "--context", args.context] if args.context else ["docker"]
path = Path(".env")
content = path.read_text()
for key, image in [
    ("PYTHON_IMAGE", "reporeaper-python:local"),
    ("NODE_IMAGE", "reporeaper-node:local"),
]:
    digest = subprocess.check_output(
        [*docker, "image", "inspect", image, "--format", "{{.Id}}"],
        text=True,
    ).strip()
    lines = [line for line in content.splitlines() if not line.startswith(key + "=")]
    content = "\n".join(lines) + f"\n{key}={digest}\n"
path.write_text(content)
print("Pinned Python/Node runtime digests in ignored local deployment config")
