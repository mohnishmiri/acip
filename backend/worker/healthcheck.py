"""Liveness check for the worker: heartbeat must be younger than WORKER_HEARTBEAT_MAX_AGE seconds."""

import os
import sys
import time
from pathlib import Path

path = Path(os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/acip-worker-heartbeat"))
max_age = float(os.environ.get("WORKER_HEARTBEAT_MAX_AGE", "300"))
if not path.exists() or time.time() - path.stat().st_mtime > max_age:
    print("worker heartbeat stale")
    sys.exit(1)
print("ok")
