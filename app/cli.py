import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from .config import Config
from .db import connect, migrate
from .security import hash_password


def cmd_migrate(cfg, args):
    db = connect(cfg.database_path)
    applied = migrate(db)
    print("Applied migrations:", ", ".join(applied) if applied else "none (already up to date)")


def cmd_seed(cfg, args):
    from datagen.load import load_dataset
    path = Path(cfg.database_path)
    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
    db = connect(cfg.database_path)
    migrate(db)
    if db.execute("SELECT COUNT(*) FROM learner").fetchone()[0]:
        sys.exit("Database already contains data. Re-run with --reset to rebuild it.")
    result = load_dataset(db, args.data_dir or cfg.data_dir)
    print(json.dumps(result, indent=2))


def cmd_demo_users(cfg, args):
    db = connect(cfg.database_path)
    password = args.password or os.environ.get("DEMO_USER_PASSWORD") or secrets.token_urlsafe(12)
    picks = {
        "platform_admin": "SELECT user_id, email FROM app_user WHERE role='platform_admin' ORDER BY user_id LIMIT 1",
        "academic_admin": "SELECT user_id, email FROM app_user WHERE role='academic_admin' ORDER BY user_id LIMIT 1",
        "support_staff": "SELECT user_id, email FROM app_user WHERE role='support_staff' ORDER BY user_id LIMIT 1",
        "instructor": "SELECT u.user_id, u.email FROM app_user u JOIN course c ON c.instructor_id = u.instructor_id "
                      "JOIN completion_record r ON r.course_id = c.course_id WHERE u.role='instructor' "
                      "GROUP BY u.user_id ORDER BY COUNT(*) DESC, u.user_id LIMIT 1",
        "learner": "SELECT u.user_id, u.email FROM app_user u JOIN credential c ON c.learner_id = u.learner_id "
                   "WHERE u.role='learner' GROUP BY u.user_id ORDER BY COUNT(*) DESC, u.user_id LIMIT 1",
    }
    hashed = hash_password(password)
    accounts = {}
    if not args.json:
        print(f"Demo accounts (password for all: {password})")
    for role, sql in picks.items():
        row = db.execute(sql).fetchone()
        if row is None:
            if not args.json:
                print(f"  {role:<15} no account available in the dataset")
            continue
        db.execute("UPDATE app_user SET password_hash = ? WHERE user_id = ?", (hashed, row["user_id"]))
        accounts[role] = row["email"]
        if not args.json:
            print(f"  {role:<15} {row['email']}")
    if args.json:
        print(json.dumps({"password": password, "accounts": accounts}))


def cmd_serve(cfg, args):
    from . import create_app
    app = create_app(cfg)
    app.run(host=args.host or os.environ.get("HOST", "127.0.0.1"), port=int(args.port or os.environ.get("PORT", 5000)),
            debug=False, threaded=True)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate").set_defaults(func=cmd_migrate)
    seed = sub.add_parser("seed")
    seed.add_argument("--data-dir")
    seed.add_argument("--reset", action="store_true")
    seed.set_defaults(func=cmd_seed)
    demo = sub.add_parser("demo-users")
    demo.add_argument("--password")
    demo.add_argument("--json", action="store_true", help="machine-readable output for scripts")
    demo.set_defaults(func=cmd_demo_users)
    serve = sub.add_parser("serve")
    serve.add_argument("--host")
    serve.add_argument("--port")
    serve.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    args.func(Config.from_env(), args)


if __name__ == "__main__":
    main()
