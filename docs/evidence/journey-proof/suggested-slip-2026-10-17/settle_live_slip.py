"""The authorized settlement read for slip a0dce8dd on the live backend: snapshot every QA slip and
leg row, sign in as the QA account, GET /api/v1/me/slips once (the read that settles), snapshot,
read again (list and single), snapshot, and verify each leg's stored settlement against the stored
regulation-time scores and the rule. Writes evidence to argv[1]; prints no token."""
import json, subprocess, sys, datetime, httpx
API = "http://127.0.0.1:8000"; DB = "soccer_predictions"; SLIP = "a0dce8dd-8b7b-466e-b1f2-77b41a860cc9"; OUT = sys.argv[1]
QA = {"email": "qa.expert@predictions-local.dev", "password": "local-only-e2e-fixture"}   # the repository's own local fixture
def psql(sql):
    out = subprocess.run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "soccer_predictions_postgres",
                          "psql", "-U", "postgres", "-d", DB, "-tAc", sql], capture_output=True, text=True, check=True)
    return [l for l in out.stdout.splitlines() if l]
def snapshot():
    slips = [json.loads(l) for l in psql("select json_build_object('id',id,'status',status,'state',state,'settled_at',settled_at,'updated_at',updated_at)::text from users.selection_slips order by created_at")]
    legs = [json.loads(l) for l in psql("select json_build_object('id',id,'slip_id',slip_id,'match_id',match_id,'market_id',market_id,'outcome',outcome,'line',line,'state',state,'settled_at',settled_at,'settlement',settlement,'updated_at',updated_at)::text from users.selection_slip_legs order by slip_id, position")]
    hashes = dict(l.split("|") for l in psql("select 'slips', md5(string_agg(to_jsonb(s)::text, '|' order by id)) from users.selection_slips s union all select 'legs', md5(string_agg(to_jsonb(g)::text, '|' order by id)) from users.selection_slip_legs g"))
    return {"taken_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "slips": slips, "legs": legs, "hashes": hashes}
health = httpx.get(API + "/health", timeout=10).json()
assert health.get("database") == DB, health
scores = {l.split("|")[0]: l.split("|")[1:] for l in psql("select r.match_id, r.home_score, r.away_score, r.home_score_ft, r.away_score_ft, r.result_metadata->>'beyond_regulation' from predictions.match_results r where r.match_id in ('4e1e2bdc-9ebb-40f0-9309-49352f213f22','be26cb61-3f69-4856-9846-dd019ed5498d')")}
before = snapshot()
login = httpx.post(API + "/api/v1/auth/login", json=QA, timeout=15); login.raise_for_status()
token = login.json().get("access_token") or login.json().get("accessToken") or login.json().get("token"); auth = {"Authorization": f"Bearer {token}"}
read_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
first = httpx.get(API + "/api/v1/me/slips", headers=auth, timeout=30); first.raise_for_status()
after_first = snapshot()
second = httpx.get(API + "/api/v1/me/slips", headers=auth, timeout=30); second.raise_for_status()
single = httpx.get(API + f"/api/v1/me/slips/{SLIP}", headers=auth, timeout=30); single.raise_for_status()
after_second = snapshot()
def rows(snap, key): return {r["id"]: r for r in snap[key]}
slip_before, slip_after = rows(before, "slips")[SLIP], rows(after_first, "slips")[SLIP]
other_changed = [s for s in before["slips"] if s["id"] != SLIP and rows(after_first, "slips")[s["id"]] != s]
legs_after = [g for g in after_first["legs"] if g["slip_id"] == SLIP]
expected = {}
for g in legs_after:
    h, a = int(scores[g["match_id"]][0]), int(scores[g["match_id"]][1]); line = float(g["line"])
    if g["market_id"] == "away_team_goals": expected[g["id"]] = ("won" if (a < line if g["outcome"] == "under" else a > line) else "lost", f"away goals {a} vs line {line:g}")
    elif g["market_id"] == "total_goals": expected[g["id"]] = ("won" if ((h + a) > line if g["outcome"] == "over" else (h + a) < line) else "lost", f"total goals {h+a} vs line {line:g}")
verification = [{"leg": g["market_id"] + ":" + g["outcome"] + "@" + str(g["line"]), "stored_state": g["state"], "stored_actual": (g["settlement"] or {}).get("actual"),
                 "expected_from_scores": expected[g["id"]][0], "basis": expected[g["id"]][1], "agree": g["state"] == expected[g["id"]][0]} for g in legs_after]
report = {"read_at": read_at, "slip_before": slip_before, "slip_after_first_read": slip_after, "slip_after_second_read": rows(after_second, "slips")[SLIP],
          "legs_after_first_read": verification, "other_slips_changed_by_the_read": [s["id"][:8] for s in other_changed],
          "first_read_changed_rows": before["hashes"] != after_first["hashes"], "second_read_changed_rows": after_first["hashes"] != after_second["hashes"],
          "updated_at_moved_on_second_read": [s["id"][:8] for s, t in zip(after_first["slips"], after_second["slips"]) if s["updated_at"] != t["updated_at"]],
          "single_read_equals_list_entry": single.json() == next(s for s in second.json()["slips"] if s["id"] == SLIP),
          "stored_scores": {k: v for k, v in scores.items()}}
for name, obj in (("before.json", before), ("after-first-read.json", after_first), ("after-second-read.json", after_second),
                  ("response-first-read.json", first.json()), ("response-second-read.json", second.json()), ("response-single-read.json", single.json()), ("summary.json", report)):
    json.dump(obj, open(f"{OUT}/{name}", "w"), indent=2, default=str)
print(json.dumps(report, indent=1, default=str))
