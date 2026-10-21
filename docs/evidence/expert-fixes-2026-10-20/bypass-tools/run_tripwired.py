"""Run a pytest command behind the guard tests' own tripwire BOOT (extracted from test_target_guard.py),
with a dead-port, unapproved environment. Prints exit code, tripwire entries and the tail of the output."""
import ast, json, os, socket, subprocess, sys
from pathlib import Path
BACKEND = Path(sys.argv[1]); args = sys.argv[2:]
src = (BACKEND / "tests/core/test_target_guard.py").read_text()
BOOT = next(n.value.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "BOOT")
def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
pg, rd = free(), free()
log = Path(os.environ["SCRATCH_LOG"]); log.write_text("")
env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
env.update(PYTHONDONTWRITEBYTECODE="1", GUARD_TRIPWIRE_LOG=str(log),
           DATABASE_URL=f"postgresql://postgres@127.0.0.1:{pg}/unapproved_db",
           TEST_DATABASE_URL=f"postgresql://postgres@127.0.0.1:{pg}/unapproved_db",
           POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT=str(pg), POSTGRES_DB="unapproved_db",
           REDIS_URL=f"redis://127.0.0.1:{rd}/0", REDIS_HOST="127.0.0.1", REDIS_PORT=str(rd),
           SYNC_SCHEDULER_ENABLED="false", EMAIL_ENABLED="false")
out = subprocess.run([sys.executable, "-c", BOOT, "pytest", *args], cwd=BACKEND, capture_output=True, text=True, timeout=240, env=env)
entries = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
text = (out.stdout + out.stderr).replace(str(Path.home()), "~")
print("--- output tail ---"); print("\n".join(text.strip().splitlines()[-int(os.environ.get("TAIL","4")):]))
print(f"exit={out.returncode}")
print("tripwire entries:", json.dumps(entries))
print("REFUSED" in text and "refusal printed" or "no refusal printed", "| CANARY printed" if "CANARY" in text else "| no CANARY")
