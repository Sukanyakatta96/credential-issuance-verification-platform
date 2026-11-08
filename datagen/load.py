import csv
import json
from pathlib import Path

from .schema_spec import ENTITIES, TABLE_ORDER

CASTERS = {"integer": int, "number": float}


def read_table(csv_dir: Path, table: str) -> list[dict]:
    types = {f["name"]: f["type"] for f in ENTITIES[table]["fields"]}
    rows = []
    with (csv_dir / f"{table}.csv").open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = {}
            for name, value in raw.items():
                if value == "":
                    row[name] = None
                else:
                    caster = CASTERS.get(types.get(name))
                    row[name] = caster(value) if caster else value
            rows.append(row)
    return rows


def load_dataset(db, data_dir: str) -> dict:
    csv_dir = Path(data_dir) / "csv"
    if not csv_dir.is_dir():
        raise FileNotFoundError(f"No CSV dataset found in {csv_dir}. Run the generator first.")
    counts, rejected = {}, 0
    db.execute("PRAGMA synchronous = OFF")
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("PRAGMA defer_foreign_keys = ON")
        for table in TABLE_ORDER:
            fields = [f["name"] for f in ENTITIES[table]["fields"]]
            rows = read_table(csv_dir, table)
            sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})"
            if table == "credential":
                inserted = 0
                for number, row in enumerate(rows, start=1):
                    try:
                        db.execute("SAVEPOINT row_insert")
                        db.execute(sql, [row[f] for f in fields])
                        db.execute("RELEASE row_insert")
                        inserted += 1
                    except Exception as exc:
                        db.execute("ROLLBACK TO row_insert")
                        db.execute("RELEASE row_insert")
                        db.execute(
                            "INSERT INTO import_rejection (source_file, row_number, record_key, reason, raw_json) VALUES (?,?,?,?,?)",
                            ("credential.csv", number, row["credential_id"], str(exc), json.dumps(row, sort_keys=True)))
                        rejected += 1
                counts[table] = inserted
            else:
                db.executemany(sql, [[row[f] for f in fields] for row in rows])
                counts[table] = len(rows)
        manifest = json.loads((Path(data_dir) / "manifest.json").read_text(encoding="utf-8"))
        # id_counter must continue from the seeded values so new IDs never collide
        for (name, year), value in _counters(db).items():
            db.execute("INSERT INTO id_counter (counter_name, counter_year, last_value) VALUES (?,?,?) "
                       "ON CONFLICT (counter_name, counter_year) DO UPDATE SET last_value = MAX(last_value, excluded.last_value)",
                       (name, year, value))
        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after load: {len(violations)}")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally:
        db.execute("PRAGMA synchronous = NORMAL")
    return {"loaded": counts, "rejected_rows": rejected, "manifest_seed": manifest["seed"]}


def _counters(db):
    def maxnum(sql):
        value = db.execute(sql).fetchone()[0]
        return int(value) if value else 0
    return {
        ("learner", 0): maxnum("SELECT MAX(CAST(substr(learner_id, 5) AS INTEGER)) FROM learner"),
        ("course", 0): maxnum("SELECT MAX(CAST(substr(course_id, 5) AS INTEGER)) FROM course"),
        ("rule", 0): maxnum("SELECT MAX(CAST(substr(rule_id, 5) AS INTEGER)) FROM credential_rule"),
        ("issuer", 0): maxnum("SELECT MAX(CAST(substr(issuer_id, 5) AS INTEGER)) FROM issuer"),
        ("assignment", 0): maxnum("SELECT MAX(CAST(substr(assignment_id, 5) AS INTEGER)) FROM rule_issuer_assignment"),
        ("user", 0): maxnum("SELECT MAX(CAST(substr(user_id, 5) AS INTEGER)) FROM app_user"),
        ("credential", 2026): maxnum("SELECT MAX(CAST(substr(credential_id, 10) AS INTEGER)) FROM credential WHERE credential_id LIKE 'CRD-2026-%'"),
        ("verification", 2026): maxnum("SELECT MAX(CAST(substr(verification_id, 10) AS INTEGER)) FROM verification_request WHERE verification_id LIKE 'VER-2026-%'"),
    }
