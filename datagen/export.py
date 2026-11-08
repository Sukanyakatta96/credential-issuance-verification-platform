import csv
import hashlib
import json
from pathlib import Path

from .generator import GENERATOR_VERSION, Dataset, Params
from .schema_spec import ENTITIES, TABLE_ORDER

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
SQL_BATCH = 400


def columns(table):
    return [f["name"] for f in ENTITIES[table]["fields"]]


def _csv_value(value):
    return "" if value is None else value


def write_csv(path: Path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow([_csv_value(row.get(f)) for f in fields])


def write_json(path: Path, rows):
    path.write_text(json.dumps(rows, separators=(",", ":"), ensure_ascii=True), encoding="utf-8")


def sql_literal(value):
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def write_sql_inserts(handle, table, fields, rows):
    column_list = ", ".join(fields)
    batch = []
    for row in rows:
        batch.append("(" + ", ".join(sql_literal(row.get(f)) for f in fields) + ")")
        if len(batch) >= SQL_BATCH:
            handle.write(f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(batch) + ";\n")
            batch = []
    if batch:
        handle.write(f"INSERT INTO {table} ({column_list}) VALUES\n" + ",\n".join(batch) + ";\n")


def split_duplicate_credentials(rows):
    seen, accepted, rejected = set(), [], []
    for number, row in enumerate(rows, start=1):
        if row["credential_id"] in seen:
            rejected.append((number, row))
        else:
            seen.add(row["credential_id"])
            accepted.append(row)
    return accepted, rejected


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_dataset(dataset: Dataset, params: Params, out_dir: Path, formats=("csv", "json", "sql"), command=""):
    out_dir.mkdir(parents=True, exist_ok=True)
    gt_dir = out_dir / "ground_truth"
    gt_dir.mkdir(exist_ok=True)
    if "csv" in formats:
        (out_dir / "csv").mkdir(exist_ok=True)
        for table in TABLE_ORDER:
            write_csv(out_dir / "csv" / f"{table}.csv", columns(table), dataset.tables[table])
    if "json" in formats:
        (out_dir / "json").mkdir(exist_ok=True)
        for table in TABLE_ORDER:
            write_json(out_dir / "json" / f"{table}.json", [{c: r.get(c) for c in columns(table)} for r in dataset.tables[table]])
    if "sql" in formats:
        (out_dir / "sql").mkdir(exist_ok=True)
        schema = "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS_DIR.glob("*.sql")))
        (out_dir / "sql" / "schema.sql").write_text(schema, encoding="utf-8")
        accepted, rejected = split_duplicate_credentials(dataset.tables["credential"])
        with (out_dir / "sql" / "seed.sql").open("w", encoding="utf-8") as handle:
            handle.write("PRAGMA foreign_keys = ON;\nPRAGMA defer_foreign_keys = ON;\nBEGIN;\n")
            for table in TABLE_ORDER:
                rows = accepted if table == "credential" else dataset.tables[table]
                write_sql_inserts(handle, table, columns(table), rows)
            for (name, year), value in sorted(dataset.counters.items()):
                handle.write(f"INSERT INTO id_counter (counter_name, counter_year, last_value) VALUES "
                             f"({sql_literal(name)}, {year}, {value});\n")
            for number, row in rejected:
                handle.write("INSERT INTO import_rejection (source_file, row_number, record_key, reason, raw_json) VALUES "
                             f"('credential.csv', {number}, {sql_literal(row['credential_id'])}, "
                             "'UNIQUE constraint failed: credential.credential_id', "
                             f"{sql_literal(json.dumps(row, sort_keys=True))});\n")
            handle.write("COMMIT;\n")

    gt_fields = ["ground_truth_id", "issue_type", "entity_type", "entity_id", "related_entity_id", "source_file", "description"]
    write_csv(gt_dir / "ground_truth.csv", gt_fields, dataset.ground_truth)
    write_json(gt_dir / "ground_truth.json", dataset.ground_truth)
    decision_fields = ["verification_id", "expected_result_status", "expected_identity_status", "expected_integrity_ok"]
    write_csv(gt_dir / "ground_truth_expected_decisions.csv", decision_fields, dataset.decisions)
    write_json(gt_dir / "ground_truth_expected_decisions.json", dataset.decisions)

    (out_dir / "data_dictionary.json").write_text(json.dumps(
        {t: {"entity": e["entity"], "primary_key": e["pk"], "description": e["description"],
             "foreign_keys": [{"column": c, "references": r} for c, r in e["foreign_keys"]],
             "fields": e["fields"]} for t, e in ENTITIES.items()}, indent=2), encoding="utf-8")
    source_manifest = {
        "external_data_used": False,
        "summary": "All records are synthetic and generated programmatically from a fixed seed. No external dataset, "
                   "scraped content or personal information was used.",
        "embedded_reference_lists": ["given names", "family names", "course topics", "organisation names"],
        "embedded_list_provenance": "Written by the author for this project; names are common, generic words and do not "
                                    "identify any real individual or institution. Email domains use reserved .example TLD.",
        "schema_inspiration": ["Open Badges 3.0 / W3C Verifiable Credentials data model (concepts only, no data copied)"],
        "license_of_generated_data": "Same as the repository; free to redistribute.",
    }
    (out_dir / "source_manifest.json").write_text(json.dumps(source_manifest, indent=2), encoding="utf-8")

    files = {}
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name not in ("manifest.json",) and not path.name.startswith("validation_") \
                and path.name != "reproducibility_report.json":
            files[str(path.relative_to(out_dir))] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest = {
        "generator": "datagen", "generator_version": GENERATOR_VERSION, "command": command,
        "seed": params.seed,
        "parameters": {"learners": params.learners, "courses": params.courses, "credentials": params.credentials,
                       "verifications": params.verifications},
        "signing_secret_note": "Issuer public keys derive from SIGNING_MASTER_SECRET; use the same value to reproduce checksums.",
        "row_counts": {t: len(dataset.tables[t]) for t in TABLE_ORDER},
        "ground_truth_rows": len(dataset.ground_truth), "meta": dataset.meta, "files": files,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=False), encoding="utf-8")
    return manifest


def checksums_of(out_dir: Path) -> dict:
    return {str(p.relative_to(out_dir)): sha256_file(p) for p in sorted(out_dir.rglob("*"))
            if p.is_file() and not p.name.startswith("validation_") and p.name != "reproducibility_report.json"}
