"""Classify the historical QA-harness predictions as test data. Run once, deliberately.

WHY THIS IS A SCRIPT AND NOT A RULE
-----------------------------------
Until now the end-to-end suite marked its own records by writing the literal "[e2e-qa]" into the
reasoning field. That text is free-form and user-controlled, so it must never decide anything at
runtime: the moment a marker in the reasoning influenced scoring, any expert could keep their own
losses off the leaderboard by typing nine characters. The runtime rule is now the stored
``is_test_data`` column, and this script is the one-off bridge that carries the historical rows
across to it.

WHAT IT MATCHES
---------------
Both conditions together, never either alone:

* ``reasoning`` starts with the historical marker, AND
* ``created_by`` is the QA account named on the command line.

The account alone would be wrong. That account also holds records a person typed by hand while
exploring the app, and those are not test data; classifying them because of who wrote them is
exactly the automatic sweep this script must not perform. Two such rows are known and are
protected by id below as well as by the marker predicate, so a change to either check still leaves
them alone:

  984df705-7d92-42f0-ba8b-be538df86a33   "nothing to say but bayern will win for sure"
  c33dd482-42c0-4f06-9f16-51ef0265a254   (reasoning NULL)

Both were withdrawn BEFORE kickoff, so under the current scoring rule neither is scored either
way; they are simply left unclassified, which is the honest state for a record nobody has
deliberately classified.

SAFETY
------
* ``--dry-run`` is the default. Nothing is written unless ``--apply`` is passed.
* Idempotent: rows already classified are counted and skipped, so a second run writes nothing.
* It never clears a classification and never touches any other column.
* Back the database up first:

    docker exec soccer_predictions_postgres pg_dump -U postgres -d soccer_predictions \\
        -n predictions > backups/before_$(date -u +%Y%m%dT%H%M%SZ).sql

USAGE
-----
    cd backend
    ./venv/bin/python scripts/classify_test_predictions.py --account <uuid>            # dry run
    ./venv/bin/python scripts/classify_test_predictions.py --account <uuid> --apply
"""

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine
from app.models.predictions import Prediction

# The application engine echoes every statement when DEBUG is on. What this script did has to be
# readable in the terminal it was run in, so the echo is turned off for this process only.
engine.echo = False

#: The marker the Playwright suite wrote into the reasoning field before the column existed. It is
#: matched as a PREFIX, which is how the harness always wrote it.
HISTORICAL_MARKER = "[e2e-qa]"

#: Records that must not be classified whatever else matches. They sit on the QA account but were
#: not produced by the harness, and the owner's instruction is explicit: leave them exactly as they
#: are. Belt and braces - the marker predicate already excludes both.
PROTECTED_IDS = (
    uuid.UUID("984df705-7d92-42f0-ba8b-be538df86a33"),
    uuid.UUID("c33dd482-42c0-4f06-9f16-51ef0265a254"),
)


def classify(account_id: uuid.UUID, apply: bool) -> int:
    """Classify the marked records of one account. Returns the number of rows changed."""
    db = SessionLocal()
    try:
        matched = (db.query(Prediction)
                   .filter(Prediction.created_by == account_id,
                           Prediction.reasoning.like(f"{HISTORICAL_MARKER}%"))
                   .order_by(Prediction.created_at.asc())
                   .all())
        # reasoning IS NULL yields NULL under LIKE rather than false, so a NULL-reasoning row can
        # never be matched here. That is the correct outcome and it is asserted, not assumed.
        protected_hits = [row for row in matched if row.id in PROTECTED_IDS]
        if protected_hits:
            raise SystemExit(
                "REFUSING TO RUN: the marker predicate matched a protected record "
                f"({', '.join(str(r.id) for r in protected_hits)}). These rows must stay "
                "unclassified; investigate before going any further.")

        already = [row for row in matched if row.is_test_data is True]
        to_change = [row for row in matched if row.is_test_data is not True]

        total_on_account = db.query(Prediction).filter(Prediction.created_by == account_id).count()
        print(f"account                       {account_id}")
        print(f"records on that account       {total_on_account}")
        print(f"matched (marker + account)    {len(matched)}")
        print(f"  already classified          {len(already)}")
        print(f"  to classify                 {len(to_change)}")
        print(f"left unclassified on account  {total_on_account - len(matched)}")
        for row in db.query(Prediction).filter(Prediction.created_by == account_id,
                                               Prediction.id.in_(PROTECTED_IDS)).all():
            print(f"  protected, untouched        {row.id}  is_test_data={row.is_test_data!r}")

        if not apply:
            print("\nDRY RUN: nothing written. Re-run with --apply to write.")
            return 0

        for row in to_change:
            row.is_test_data = True
        db.commit()
        print(f"\nAPPLIED: {len(to_change)} record(s) classified as test data.")
        return len(to_change)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--account", required=True,
                        help="UUID of the QA account whose marked records are to be classified")
    parser.add_argument("--apply", action="store_true",
                        help="actually write (without this the script only reports)")
    args = parser.parse_args()
    classify(uuid.UUID(args.account), args.apply)


if __name__ == "__main__":
    main()
