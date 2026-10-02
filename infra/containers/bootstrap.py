import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

fixture, path, phase = sys.argv[1:]
if phase == "slow_setup":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    time.sleep(20)
shutil.copytree(Path("/opt/fixtures") / fixture, Path("/work/repo"))
source = Path("/work/repo") / path
if phase == "patched":
    source.write_text(source.read_text().replace("< maximum", "<= maximum"))
if phase == "slow_test":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    time.sleep(20)
if phase == "isolation":
    assert not any(k in os.environ for k in ("RUNNER_TOKEN", "SESSION_SECRET", "DATABASE_URL"))
    assert not Path("/var/run/docker.sock").exists()
    assert not Path("/data").exists()
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1)
    except OSError:
        print("Isolation probe passed: no secrets, mounts, or network")
        sys.exit(0)
    raise AssertionError("Unexpected network access")
completed = subprocess.run(
    [sys.executable, "/opt/harness/python_check.py", str(source.parent)],
    env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"},
)
sys.exit(completed.returncode)
