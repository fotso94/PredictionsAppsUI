"""After the apply: every row outside the target set is byte-identical to the pre-apply backup
(restored into a scratch database), target rows changed only in their metadata column and
updated_at, and no table's row count moved. The backend was stopped throughout, so the backup IS
the pre-apply state. Exit 1 on any difference."""
import json, subprocess, sys

LIVE, COPY, PLAN = sys.argv[1], sys.argv[2], sys.argv[3]
rows = [json.loads(line) for line in open(PLAN)]
match_ids = {r["match_id"] for r in rows if r.get("kind") == "fixture"}
league_ids = {r["league_id"] for r in rows if r.get("kind") == "observation"}

def psql(db, sql):
    out = subprocess.run(["docker", "exec", "-i", "-e", "PGOPTIONS=-c default_transaction_read_only=on",
                          "soccer_predictions_postgres", "psql", "-U", "postgres", "-d", db, "-tAc", sql],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"psql {db} failed: {out.stderr.strip()[:200]}")
    return [line for line in out.stdout.splitlines() if line]

problems = []
tables = psql(LIVE, "select schemaname||'.'||tablename from pg_tables "
                    "where schemaname in ('users','predictions','ml_models','analytics','audit') order by 1")
for table in tables:
    live, copy = psql(LIVE, f"select count(*) from {table}")[0], psql(COPY, f"select count(*) from {table}")[0]
    if live != copy:
        problems.append(f"{table}: {copy} rows before, {live} after")
print(f"row counts compared on {len(tables)} tables")

def hashes(db, table, strip):
    sql = (f"select id, md5(to_jsonb(t.*)::text), md5(((to_jsonb(t.*) - '{strip}') - 'updated_at')::text) "
           f"from {table} t")
    return {i: (whole, stripped) for i, whole, stripped in (line.split("|") for line in psql(db, sql))}

for table, strip, targets in (("predictions.leagues", "league_metadata", league_ids),
                              ("predictions.matches", "match_metadata", match_ids)):
    live, copy = hashes(LIVE, table, strip), hashes(COPY, table, strip)
    if set(live) != set(copy):
        problems.append(f"{table}: ids differ: {sorted(set(live) ^ set(copy))[:4]}")
    untouched = changed = 0
    for rid in set(live) & set(copy):
        if rid in targets:
            if live[rid][1] != copy[rid][1]:
                problems.append(f"{table} {rid}: a target row changed outside its metadata column")
            changed += 1
        else:
            if live[rid][0] != copy[rid][0]:
                problems.append(f"{table} {rid}: an untouched row changed")
            untouched += 1
    print(f"{table}: {untouched} untouched rows identical, {changed} target rows metadata-only")
for p in problems:
    print("DIFFERS:", p)
sys.exit(1 if problems else 0)
