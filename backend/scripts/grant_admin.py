"""
Promote an existing user to administrator, or list who already is one.

Public registration deliberately refuses `role=admin`: that endpoint is unauthenticated and returns a
signed token, so accepting the field let anyone mint an administrator and be logged in as one in the
same request. Administrators are granted here instead, which requires access to the database — the
same access that could grant one with SQL anyway, so this adds no new privilege, it just makes the
step deliberate and auditable.

    cd backend
    ./venv/bin/python scripts/grant_admin.py --list
    ./venv/bin/python scripts/grant_admin.py --email you@example.com --dry-run
    ./venv/bin/python scripts/grant_admin.py --email you@example.com
    ./venv/bin/python scripts/grant_admin.py --email someone@example.com --revoke
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

from app.db.session import SessionLocal
from app.models.users import User, UserType


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", help="email address of an existing user")
    parser.add_argument("--list", action="store_true", help="show the current administrators and exit")
    parser.add_argument("--revoke", action="store_true", help="demote to a regular user instead of promoting")
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()

    if not args.list and not args.email:
        parser.error("give --email, or --list to see the current administrators")

    db = SessionLocal()
    try:
        if args.list:
            admins = db.query(User).filter(User.user_type == UserType.ADMIN,
                                           User.deleted_at.is_(None)).order_by(User.created_at).all()
            if not admins:
                print("No administrators exist. Promote one with:")
                print("  ./venv/bin/python scripts/grant_admin.py --email <an existing user>")
                return 0
            print(f"{len(admins)} administrator(s):")
            for admin in admins:
                print(f"  {admin.email:45} since {admin.created_at:%Y-%m-%d}")
            return 0

        user = db.query(User).filter(User.email == args.email, User.deleted_at.is_(None)).first()
        if user is None:
            print(f"No user with email {args.email}. They must register first, then be promoted here.")
            return 1

        target = UserType.REGULAR if args.revoke else UserType.ADMIN
        if user.user_type == target:
            print(f"{user.email} is already {target.value}; nothing to do.")
            return 0

        verb = "demote" if args.revoke else "promote"
        print(f"{verb}: {user.email}  {user.user_type.value} -> {target.value}")
        if args.dry_run:
            print("dry run - nothing was written")
            return 0

        user.user_type = target
        user.updated_at = datetime.utcnow()
        db.commit()
        print("done. They must sign in again for the new role to appear in their token.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
