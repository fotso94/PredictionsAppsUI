"""Compare a live report-only plan with the rehearsed plan on the CORRECTED fields only.

Deferral counters, next-ask times and audit stamps move between the two runs and are expected to;
what was rehearsed and approved is the corrected state. Exit 1 on any difference there.
"""
import json, sys

OBS_AFTER = ("state", "rows", "provider", "asked_at", "times_asked", "count_quality",
             "reconstructed", "first_asked_at", "last_answered_at", "times_asked_at_correction")
FIX_AFTER = ("attempts", "attempts_quality", "attempts_at_correction", "last_attempt_at", "archive")

def rows(path):
    out = [json.loads(line) for line in open(path)]
    return out[0], {("obs", r["league"], r["date"]): r for r in out if r.get("kind") == "observation"}, \
           {("fix", r["match_id"]): r for r in out if r.get("kind") == "fixture"}

def reduced(kind, row, outcome_replaced=False):
    after = row.get("after") or {}
    if kind == "obs":
        core = {k: after.get(k) for k in OBS_AFTER} if row.get("after") is not None else None
        return {"class": row.get("class"), "quality": row.get("quality"),
                "reconstructed": row.get("reconstructed"), "removed_asks": row.get("removed_asks"),
                "after": core}
    core = {k: after.get(k) for k in FIX_AFTER}
    core["first_attempt_at_present"] = "first_attempt_at" in after
    if outcome_replaced:
        # Only where the repair itself rewrote the outcome (the closed relisting's false
        # "api_football answered" sentence) is the outcome a corrected field. Everywhere else it is
        # the genuine deferral bookkeeping the scheduler keeps moving, which the plan says will
        # differ between the rehearsal and the live run.
        detail = str(after.get("last_outcome_detail") or "")
        core.update(last_outcome=after.get("last_outcome"), last_outcome_at=after.get("last_outcome_at"),
                    detail_prefix=detail.split(" (reconstructed on")[0])
    return {"group": row.get("group"), "quality": row.get("quality"),
            "removed_attempts": row.get("removed_attempts"), "after": core}

live_header, live_obs, live_fix = rows(sys.argv[1])
reh_header, reh_obs, reh_fix = rows(sys.argv[2])
problems = []
for name, want, got in (("observations", 13, live_header.get("observations")),
                        ("fixtures", 66, live_header.get("fixtures")),
                        ("skipped", 0, live_header.get("skipped"))):
    if got != want:
        problems.append(f"header {name}: {got}, wanted {want}")
method = live_header.get("synced_row_method") or {}
if method.get("agree") != method.get("checked") or method.get("disagree"):
    problems.append(f"synced-row method no longer agrees everywhere: {method}")
if set(live_obs) != set(reh_obs) or set(live_fix) != set(reh_fix):
    problems.append(f"target sets differ: obs {sorted(set(live_obs) ^ set(reh_obs))}, "
                    f"fixtures {sorted(set(live_fix) ^ set(reh_fix))}")
for key in sorted(set(live_obs) & set(reh_obs)):
    a, b = reduced("obs", live_obs[key]), reduced("obs", reh_obs[key])
    if a != b:
        problems.append(f"{key}: live {a} != rehearsed {b}")
for key in sorted(set(live_fix) & set(reh_fix)):
    replaced = "(reconstructed on" in str((reh_fix[key].get("after") or {}).get("last_outcome_detail") or "")
    a, b = reduced("fix", live_fix[key], replaced), reduced("fix", reh_fix[key], replaced)
    if a != b:
        problems.append(f"{key}: live {a} != rehearsed {b}")
asks = sum(r.get("removed_asks") or 0 for r in live_obs.values())
attempts = sum(r.get("removed_attempts") or 0 for r in live_fix.values())
if (asks, attempts) != (32, 167):
    problems.append(f"removal totals {asks}/{attempts}, wanted 32/167")
print(f"compared {len(live_obs)} observations and {len(live_fix)} fixtures; "
      f"removals {asks} asks / {attempts} attempts")
for p in problems:
    print("DIFFERS:", p)
sys.exit(1 if problems else 0)
