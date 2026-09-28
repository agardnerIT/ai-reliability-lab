"""
Runs once after the dev container is created.
Installs Python dependencies and configures the dtctl context.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)


# Install dependencies
run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", ROOT / "requirements.txt"])

# Load .env
env_file = ROOT / ".devcontainer" / ".env"
env = {}
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()

dt_tenant = env.get("DT_TENANT") or os.environ.get("DT_TENANT", "")
platform_token = env.get("DTCTL_PLATFORM_TOKEN") or os.environ.get("DTCTL_PLATFORM_TOKEN", "")

if dt_tenant and platform_token:
    run([
        "dtctl", "config", "set-context", "lab",
        "--environment", f"https://{dt_tenant}.apps.dynatrace.com",
        "--token-ref", "lab-token",
    ])
    run(["dtctl", "config", "set-credentials", "lab-token", "--token", platform_token])
    print("dtctl context 'lab' configured.")
else:
    print("DT_TENANT or DTCTL_PLATFORM_TOKEN not set in .devcontainer/.env — skipping dtctl setup.")
    print("Fill in .devcontainer/.env and re-run: python .devcontainer/postCreate.py")
