"""Settlement proof on the isolated copy: open the QA account's slips through the isolated API
(which settles them on read), snapshot the slip tables before, after the first read and after a
second read, and show the second read changed nothing. Refuses any backend that is not serving the
e2e clone. Writes its evidence to the directory given as argv[1]; prints no token."""
import json, subprocess, sys, datetime, httpx

API = "http://127.0.0.1:8001"
DB = "soccer_predictions_e2e"
OUT = sys.argv[1]
QA = {"email": "qa.expert@predictions-local.dev", "password": "local-only-e2e-fixture"}  # the repo's own fixture

def psql(sql):
    out = subprocess.run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                          "soccer_predictions_postgres", "psql", "-U", "postgres", "-d", DB, "-tAc", sql],
                         capture_output=True, text=True, check=True)
    return [l for l in out.stdout.splitlines() if l]

def snapshot():
    slips = [json.loads(l) for l in psql("select json_build_object('id',id,'status',status,'state',state,"
        "'settled_at',settled_at,'updated_at',updated_at,'recorded_at',recorded_at)::text from users.selection_slips order by created_at")]
    legs = [json.loads(l) for l in psql("select json_build_object('id',id,'slip_id',slip_id,'match_id',match_id,"
        "'market_id',market_id,'outcome',outcome,'line',line,'state',state,'settled_at',settled_at,'settlement',settlement,"
        "'updated_at',updated_at)::text from users.selection_slip_legs order by slip_id, position")]
    hashes = dict(l.split("|") for l in psql(
        "select 'slips', md5(string_agg(to_jsonb(s)::text, '|' order by id)) from users.selection_slips s "
        "union all select 'legs', md5(string_agg(to_jsonb(g)::text, '|' order by id)) from users.selection_slip_legs g"))
    tables = psql("select schemaname||'.'||tablename from pg_tables where schemaname in "
                  "('users','predictions','ml_models','analytics','audit') order by 1")
    counts = {t: int(psql(f"select count(*) from {t}")[0]) for t in tables}
    return {"taken_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "slips": slips, "legs": legs,
            "hashes": hashes, "row_counts": counts}

health = httpx.get(API + "/health", timeout=10).json()
if health.get("database") != DB:
    raise SystemExit(f"refusing: {API} serves {health.get('database')!r}, not the e2e clone")
print("backend:", API, "database", health["database"], "commit", (health.get("source") or {}).get("commit", "")[:8])

before = snapshot()
login = httpx.post(API + "/api/v1/auth/login", json=QA, timeout=10)
login.raise_for_status()
token = login.json().get("access_token") or login.json().get("accessToken") or login.json().get("token")
auth = {"Authorization": f"Bearer {token}"}

first = httpx.get(API + "/api/v1/me/slips", headers=auth, timeout=30)
first.raise_for_status()
after_first = snapshot()
second = httpx.get(API + "/api/v1/me/slips", headers=auth, timeout=30)
second.raise_for_status()
singles = {s["id"]: httpx.get(API + f"/api/v1/me/slips/{s['id']}", headers=auth, timeout=30).json() for s in first.json()["slips"]}
after_second = snapshot()

def states(snap):
    return {s["id"][:8]: (s["state"], s["settled_at"]) for s in snap["slips"]}
report = {
    "before": states(before), "after_first_read": states(after_first), "after_second_read": states(after_second),
    "legs_after_first": [(g["slip_id"][:8], g["market_id"], g["outcome"], g["line"], g["state"], (g["settlement"] or {}).get("actual")) for g in after_first["legs"]],
    "first_read_changed_rows": before["hashes"] != after_first["hashes"],
    "second_read_changed_rows": after_first["hashes"] != after_second["hashes"],
    "second_read_changed_any_table": after_first["row_counts"] != after_second["row_counts"],
    "updated_at_moved_on_second_read": [s["id"][:8] for s, t in zip(after_first["slips"], after_second["slips"]) if s["updated_at"] != t["updated_at"]],
    "first_response_equals_second_response": first.json() == second.json(),
    "single_reads_match_list": all(singles[s["id"]] == s for s in second.json()["slips"]),
    "row_counts_moved_between_before_and_after": {t: (before["row_counts"][t], after_second["row_counts"][t]) for t in before["row_counts"] if before["row_counts"][t] != after_second["row_counts"][t]},
}
for name, obj in (("before.json", before), ("after-first-read.json", after_first), ("after-second-read.json", after_second),
                  ("response-first-read.json", first.json()), ("response-second-read.json", second.json()), ("summary.json", report)):
    with open(f"{OUT}/{name}", "w") as f:
        json.dump(obj, f, indent=2, default=str)
print(json.dumps(report, indent=1, default=str))
