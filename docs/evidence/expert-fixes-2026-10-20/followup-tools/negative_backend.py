"""Negative demonstrations: the REAL pytest entry point (`python -m pytest`, run with runpy exactly as -m
does) over the whole suite, in a subprocess behind the guard tests' own tripwire (BOOT, extracted from
tests/core/test_target_guard.py up to its mode switch): every socket connect and name lookup,
psycopg2.connect and httpx request is recorded and BLOCKED, and imports of app.main, tests.conftest and
app.db.session are recorded. Every unsafe target is on a port nothing listens on or on TEST-NET-1
(192.0.2.1); the approved base names only the throwaway services guard-race-pg :5440 / guard-test-redis :6390.
usage: negative_backend.py <backend dir>"""
import ast, json, os, re, socket, subprocess, sys
from pathlib import Path

BACKEND = Path(sys.argv[1])
src = (BACKEND / "tests/core/test_target_guard.py").read_text()
BOOT = next(n.value.value for n in ast.parse(src).body
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "BOOT")
cut = BOOT.index("mode, args = sys.argv[1], sys.argv[2:]")
HARNESS = BOOT[:cut] + ("import runpy\nsys.argv = ['pytest', *sys.argv[1:]]\n"
                        "runpy.run_module('pytest', run_name='__main__', alter_sys=True)\n")

def free():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

URL_PW, ENV_PW = "url-password-not-real", "subprocess-password-not-real"
BASE = dict(TEST_DATABASE_URL=f"postgresql://postgres:{URL_PW}@127.0.0.1:5440/forecast_race_test",
            POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT="5440", POSTGRES_DB="forecast_race_test",
            POSTGRES_USER="postgres", POSTGRES_PASSWORD=ENV_PW, REDIS_HOST="127.0.0.1", REDIS_PORT="6390",
            SYNC_SCHEDULER_ENABLED="false", EMAIL_ENABLED="false")
ROLES = ("REDIS_DB_SESSIONS", "REDIS_DB_PREDICTIONS", "REDIS_DB_EXPERT_TOOLS", "REDIS_DB_ML_MODELS",
         "REDIS_DB_MATCH_DATA", "REDIS_DB_RATE_LIMIT")

# The secrets of the backend/.env the settings fall back to (a link to the main checkout's live
# configuration): read here only to check that none of them appears in any output. Never printed.
dotenv_secrets = []
for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
    if m and re.search(r"PASSWORD|SECRET|KEY|TOKEN", m.group(1), re.I):
        value = m.group(2).strip().strip('"').strip("'")
        if len(value) >= 4:
            dotenv_secrets.append(value)

def show(value):
    return None if value is None else value.replace(URL_PW, "***").replace(ENV_PW, "***")

def run(title, changes, args, expect_codes, control=False):
    log = Path(os.environ["SCRATCH_DIR"]) / "tripwire.jsonl"
    log.write_text("")
    env = dict(BASE)
    for k, v in changes.items():
        if v is None: env.pop(k, None)
        else: env[k] = v
    base = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
    full = {**base, "PYTHONDONTWRITEBYTECODE": "1", "GUARD_TRIPWIRE_LOG": str(log), **env}
    print("=" * 100)
    print(f"== {title}")
    print("   change from the approved base:", ", ".join(f"{k}={show(v)!r}" if v is not None else f"{k} unset"
                                                      for k, v in changes.items()) or "none")
    print("   $ cd <worktree>/backend && python -c <tripwire BOOT> " + " ".join(args)
          + "   (the harness then runs pytest's own __main__ via runpy, as python -m pytest does)")
    out = subprocess.run([sys.executable, "-c", HARNESS, *args], cwd=BACKEND, env=full,
                         capture_output=True, text=True, timeout=600)
    text = out.stdout + out.stderr
    entries = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    connects = [e for e in entries if e["kind"] != "import"]
    imports = [e for e in entries if e["kind"] == "import"]
    print("-- output (stdout+stderr, as the person would see it):")
    print(text.rstrip())
    print(f"-- exit={out.returncode}")
    print(f"-- tripwire: connection attempts {len(connects)}; imports of app.main/tests.conftest/app.db.session {len(imports)}")
    for e in entries:
        print(f"     {e['kind']} {e['target']}")
    codes = sorted(set(re.findall(r"^\s+\d+\. \[([a-z:_A-Z-]+)\]", text, re.M)))
    leaked = [label for label, s in (("injected URL password", URL_PW), ("injected POSTGRES_PASSWORD", ENV_PW)) if s in text]
    leaked_dotenv = sum(1 for s in dotenv_secrets if s in text)
    print(f"-- refusal codes: {codes}")
    print(f"-- credentials in the output: injected fake secrets {leaked or 'none'}; backend/.env secret values found "
          f"{leaked_dotenv} of {len(dotenv_secrets)} checked (values never printed)")
    if control:
        ok = (out.returncode == 0 and "CANARY" in text and connects and not leaked and not leaked_dotenv
              and all(e["target"].startswith(("127.0.0.1:5440", "127.0.0.1:6390", f"127.0.0.1:{DEAD}")) for e in connects))
        print(f"-- CONTROL {'HOLDS' if ok else 'FAILED'}: exit 0, the canary ran, and every attempt (all blocked) went to an approved throwaway target or the canary's dead HTTP port")
    else:
        missing = sorted(set(expect_codes) - set(codes))
        ok = (out.returncode == 78 and not entries and "REFUSED" in text and "Nothing has connected" in text
              and "CANARY" not in text and not leaked and not leaked_dotenv and not missing
              and not re.search(r"\d+ (passed|failed|error)", text) and "collected" not in text)
        print(f"-- NEGATIVE {'HOLDS' if ok else 'FAILED'}: exit 78, zero tripwire entries, refusal printed, expected codes "
              f"present{' (missing ' + str(missing) + ')' if missing else ''}, no credential, no test collected or run")
    RESULTS.append((title, out.returncode, len(connects), len(imports), ok))

RESULTS = []
DEAD = free()
SUITE = ["-q", "-p", "no:cacheprovider", "-o", "addopts=", "-rs", "tests"]
CANARY = ["-q", "-rP", "-p", "no:cacheprovider", "-o", "addopts=", "tests/core/guard_canary.py"]
on_6379 = {"REDIS_HOST": "192.0.2.1", "REDIS_PORT": "6379"}

run("CONTROL: the approved base (throwaway targets only) on the canary - the tripwire really catches what a test body reaches for",
    {"GUARD_CANARY_HTTP_URL": f"http://127.0.0.1:{DEAD}/"}, CANARY, [], control=True)
# 1. missing overrides
run("1a. missing overrides: TEST_DATABASE_URL, SYNC_SCHEDULER_ENABLED and EMAIL_ENABLED unset (the conftest default and the .env/class defaults would fill them)",
    {"TEST_DATABASE_URL": None, "SYNC_SCHEDULER_ENABLED": None, "EMAIL_ENABLED": None}, SUITE,
    ["missing:TEST_DATABASE_URL", "missing:SYNC_SCHEDULER_ENABLED", "missing:EMAIL_ENABLED"])
run("1b. missing override: REDIS_PORT unset with REDIS_HOST on TEST-NET-1 (the port would come from backend/.env)",
    {"REDIS_HOST": "192.0.2.1", "REDIS_PORT": None}, SUITE, ["missing:redis"])
# 2. live database name
run("2a. live database by name: soccer_predictions, on a port nothing listens on",
    {"TEST_DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:{DEAD}/soccer_predictions",
     "POSTGRES_PORT": str(DEAD), "POSTGRES_DB": "soccer_predictions"}, SUITE, ["live-database"])
run("2b. live database by name: soccer_predictions_dev through DATABASE_URL (POSTGRES_DB unset), on a port nothing listens on",
    {"POSTGRES_DB": None, "POSTGRES_SERVER": None, "POSTGRES_PORT": None,
     "DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:{DEAD}/soccer_predictions_dev",
     "TEST_DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:{DEAD}/soccer_predictions_dev"}, SUITE, ["live-database"])
# 3. live Redis target
run("3. live Redis server: REDIS_HOST/REDIS_PORT naming port 6379 (on TEST-NET-1)", on_6379, SUITE, ["live-redis"])
# 4. live Redis database
run("4a. a live Redis database named by URL: REDIS_URL=redis://192.0.2.1:6379/3 (REDIS_HOST/REDIS_PORT unset, REDIS_DB=3)",
    {"REDIS_HOST": None, "REDIS_PORT": None, "REDIS_URL": "redis://192.0.2.1:6379/3", "REDIS_DB": "3"}, SUITE, ["live-redis"])
run("4b. the lease tests' databases on the live server: LEASE_TEST_REDIS_URL=redis://192.0.2.1:6379/0 (the lease tests flush 0-2)",
    {"LEASE_TEST_REDIS_URL": "redis://192.0.2.1:6379/0"}, SUITE, ["live-redis"])
run("4c. the isolated pair's Redis databases 10-15 on port 6379 (TEST-NET-1), every one written down",
    {**on_6379, "REDIS_DB": "10", **{k: str(10 + i) for i, k in enumerate(ROLES)}}, SUITE, ["isolated-pair-redis"])
# 5. conflicting settings
run("5a. conflicting settings: TEST_DATABASE_URL is not the database the settings resolve to (POSTGRES_PORT on a dead port)",
    {"POSTGRES_PORT": str(DEAD)}, SUITE, ["conflict:test-vs-settings-database"])
run("5b. conflicting settings: REDIS_URL and REDIS_HOST/REDIS_PORT both set and disagreeing",
    {"REDIS_URL": f"redis://127.0.0.1:{DEAD}/0"}, SUITE, ["conflict:redis-url-vs-parts"])
run("5c. conflicting settings: TEST_DATABASE_URL whose query string redirects host, port and database",
    {"TEST_DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:5440/forecast_race_test?host=127.0.0.1&port={DEAD}&dbname=soccer_predictions"},
    SUITE, ["conflict:postgres-url", "live-database"])
run("5d. conflicting settings: the unsplit shell variable (TEST_DATABASE_URL holding the next assignments, as zsh's env $V left it)",
    {"TEST_DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:5440/forecast_race_test POSTGRES_DB=forecast_race_test REDIS_HOST=127.0.0.1"},
    SUITE, ["conflict:unsplit-value"])
run("5e. conflicting settings: two Redis roles on one database, and the race database equal to the test database",
    {"REDIS_DB_SESSIONS": "3", "REDIS_DB_PREDICTIONS": "3",
     "RACE_TEST_DATABASE_URL": f"postgresql://postgres:{URL_PW}@127.0.0.1:5440/forecast_race_test"},
    SUITE, ["conflict:redis-db-collision", "conflict:race-same-as-test"])

print("=" * 100)
print("SUMMARY (case | exit | connection attempts | recorded imports | holds)")
for title, code, c, i, ok in RESULTS:
    print(f"  {title.split(':')[0]:<10} exit={code:<3} attempts={c} imports={i} {'HOLDS' if ok else 'FAILED'}")
bad = [t for t, *_, ok in RESULTS if not ok]
print(f"{len(RESULTS) - len(bad)} of {len(RESULTS)} hold")
raise SystemExit(1 if bad else 0)
