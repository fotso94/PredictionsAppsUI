"""The backend-isolated launch entry's guard command and the fixed /health database name, over the
entry's own environment, with every socket connect and name lookup blocked and recorded. Pure."""
import ast, json, os, subprocess, sys
from pathlib import Path
W = Path(sys.argv[1]); BACKEND = W / "backend"
entry = next(c for c in json.loads((W / ".claude/launch.json").read_text())["configurations"] if c["name"] == "backend-isolated")
guard_cmd = entry["runtimeArgs"][1].partition(" && exec ")[0]
print("entry command:", entry["runtimeExecutable"], entry["runtimeArgs"][0], repr(entry["runtimeArgs"][1]))
src = (BACKEND / "tests/core/test_target_guard.py").read_text()
BOOT = next(n.value.value for n in ast.parse(src).body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "BOOT")
base = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
log = Path(os.environ["SCRATCH_LOG"]); log.write_text("")
env = {**base, **entry["env"], "PYTHONDONTWRITEBYTECODE": "1", "GUARD_TRIPWIRE_LOG": str(log)}
out = subprocess.run([sys.executable, "-c", BOOT, "cli", *guard_cmd.split()[3:], "--json"], cwd=BACKEND, env=env,
                     capture_output=True, text=True, timeout=120)
text = out.stdout + out.stderr
verdict = json.loads(text[text.index("{"):text.rindex("}") + 1])
print(f"guard over the entry's environment: exit={out.returncode} ok={verdict['ok']} codes={verdict['codes']}")
print("  targets:", "; ".join(f"{k} {v}" for k, v in verdict["targets"].items()))
print("  tripwire entries:", log.read_text().strip() or "none")
probe = r'''
import sys
def audit(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        print("BLOCKED", event, flush=True); raise OSError("blocked")
sys.addaudithook(audit)
from app.core.config import settings
from app.core.target_guard import driver_database
print("fixed /health database for this environment:", driver_database(settings.DATABASE_URL))
'''
out = subprocess.run([sys.executable, "-c", probe], cwd=BACKEND, env={**base, **entry["env"], "PYTHONDONTWRITEBYTECODE": "1"},
                     capture_output=True, text=True, timeout=120)
print(out.stdout.strip(), out.stderr.strip()[-300:] if out.returncode else "")
