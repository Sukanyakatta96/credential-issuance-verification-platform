"""Generates docs/DATA_DICTIONARY.md and docs/API_ENDPOINTS.md from the code, so documentation cannot drift."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from datagen.schema_spec import ENTITIES, RELATIONSHIPS, TABLE_ORDER  # noqa: E402


def data_dictionary() -> str:
    out = ["# Data Dictionary", "",
           "Generated from `datagen/schema_spec.py`, which also drives the CSV column order, the validator's enum and "
           "required-field checks, and a test that compares it with the real database columns.", "",
           "Conventions: timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`; dates are `YYYY-MM-DD`; percentages are 0-100; "
           "empty CSV cells are NULL; identifiers are immutable.", "", "## Relationships and cardinality", "",
           "| From | To | Cardinality | Notes |", "|---|---|---|---|"]
    out += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in RELATIONSHIPS]
    out += ["", "Load order (parents before children): " + " → ".join(f"`{t}`" for t in TABLE_ORDER), ""]
    for table in TABLE_ORDER:
        e = ENTITIES[table]
        out += [f"## {e['entity']} — `{table}`", "", e["description"], "", f"- **Primary key:** `{e['pk']}`",
                f"- **Kind:** {e['kind']}"]
        if e["foreign_keys"]:
            out.append("- **Foreign keys:** " + ", ".join(f"`{c}` → `{p}`" for c, p in e["foreign_keys"]))
        if e.get("lifecycle"):
            out.append(f"- **Lifecycle:** {e['lifecycle']}")
        out += ["", "| Field | Type | Required | Allowed values | Unit | Unique | Validation rule |", "|---|---|---|---|---|---|---|"]
        for f in e["fields"]:
            allowed = ", ".join(str(a) for a in f["allowed"]) if f["allowed"] else ""
            out.append(f"| `{f['name']}` | {f['type']} | {'yes' if f['required'] else 'no'} | {allowed} | {f['unit'] or ''} | "
                       f"{'yes' if f['unique'] else ''} | {f['rule']} |")
        out.append("")
    out += ["## Supporting tables (application only)", "",
            "- `id_counter` — atomic counters behind `CRD-YYYY-NNNNNN`, `VER-YYYY-NNNNNN` and the other generated IDs.",
            "- `import_rejection` — rows refused by database constraints during import (for example the duplicate credential IDs).",
            "- `schema_migration` — applied migration files.", "",
            "## Database-enforced rules", "",
            "Defined in `migrations/001_initial_schema.sql`: ID format `CHECK`s, enum `CHECK`s, `UNIQUE` and partial-unique indexes "
            "(one active credential per learner and rule), foreign keys, and triggers that make `audit_event`, `revocation`, "
            "`verification_request` and `assessment_attempt` append-only, make credential issuance fields immutable, allow only "
            "`active → revoked` (and only when a revocation row exists), and freeze finalised completion records.", ""]
    return "\n".join(out)


def api_endpoints() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Config(database_path=str(Path(tmp) / "docs.db"), data_dir=tmp, ground_truth_dir=tmp, jwt_secret="x" * 40,
                     jwt_ttl_minutes=5, signing_master_secret="y" * 40, public_rate_limit_per_minute=5,
                     login_max_failures=5, login_lockout_seconds=60)
        app = create_app(cfg)
        rows = []
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, sorted(r.methods))):
            if not rule.rule.startswith("/api/"):
                continue
            view = app.view_functions[rule.endpoint]
            roles = getattr(view, "allowed_roles", None)
            access = "public" if roles is None else ("any signed-in user" if len(roles) == 5 else ", ".join(roles))
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                rows.append((rule.rule, method, access))
    out = ["# API Endpoint Reference (generated)", "", "Generated from the Flask URL map and the `require_roles` decorators. "
           "See `docs/API.md` for request and response conventions.", "", "| Method | Path | Access |", "|---|---|---|"]
    out += [f"| {m} | `{p}` | {a} |" for p, m, a in rows]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "DATA_DICTIONARY.md").write_text(data_dictionary(), encoding="utf-8")
    (docs / "API_ENDPOINTS.md").write_text(api_endpoints(), encoding="utf-8")
    print("Wrote docs/DATA_DICTIONARY.md and docs/API_ENDPOINTS.md")
