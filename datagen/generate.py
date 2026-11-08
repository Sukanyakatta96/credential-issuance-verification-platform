import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from app.config import PROJECT_ROOT, load_env_file

from .export import checksums_of, export_dataset
from .generator import SCALES, Params, generate
from .validate import render_markdown, validate_dataset


def build_parser():
    p = argparse.ArgumentParser(description="Deterministic synthetic data generator for the credential platform")
    p.add_argument("--scale", choices=sorted(SCALES), default="full")
    p.add_argument("--learners", type=int)
    p.add_argument("--courses", type=int)
    p.add_argument("--credentials", type=int)
    p.add_argument("--verifications", type=int)
    p.add_argument("--seed", type=int, default=20261022)
    p.add_argument("--out", default=None, help="output directory (default data/<scale>)")
    p.add_argument("--formats", default="csv,json,sql")
    p.add_argument("--signing-secret", default=None, help="defaults to SIGNING_MASTER_SECRET from the environment/.env")
    p.add_argument("--validate", action="store_true", help="run the validation suite and write reports")
    p.add_argument("--check-reproducibility", action="store_true", help="regenerate twice and compare checksums")
    return p


def resolve_params(args) -> Params:
    import os
    load_env_file(PROJECT_ROOT / ".env")
    secret = args.signing_secret or os.environ.get("SIGNING_MASTER_SECRET", "")
    if not secret or secret.startswith("CHANGE_ME"):
        sys.exit("SIGNING_MASTER_SECRET is not configured (set it in .env or pass --signing-secret).")
    learners, courses, credentials, verifications = SCALES[args.scale]
    return Params(seed=args.seed, learners=args.learners or learners, courses=args.courses or courses,
                  credentials=args.credentials or credentials, verifications=args.verifications or verifications,
                  signing_secret=secret)


def command_line(args, params) -> str:
    return (f"python -m datagen.generate --scale {args.scale} --seed {params.seed} --learners {params.learners} "
            f"--courses {params.courses} --credentials {params.credentials} --verifications {params.verifications}")


def reproducibility_check(params, formats, primary_dir: Path, command: str) -> dict:
    primary = checksums_of(primary_dir)
    runs = []
    for attempt in (1, 2):
        with tempfile.TemporaryDirectory() as tmp:
            dataset = generate(params)
            export_dataset(dataset, params, Path(tmp), formats, command)
            runs.append({"row_counts": {t: len(r) for t, r in dataset.tables.items()}, "checksums": checksums_of(Path(tmp))})
    identical = all(run["checksums"] == primary for run in runs)
    report = {"seed": params.seed, "regenerations": 2, "identical_to_primary_output": identical,
              "files_compared": len(primary), "row_counts": runs[0]["row_counts"],
              "checksums_sha256": primary}
    (primary_dir / "reproducibility_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    args = build_parser().parse_args(argv)
    params = resolve_params(args)
    formats = tuple(f.strip() for f in args.formats.split(",") if f.strip())
    out_dir = Path(args.out) if args.out else PROJECT_ROOT / "data" / args.scale
    if out_dir.exists():
        shutil.rmtree(out_dir)
    command = command_line(args, params)
    started = time.time()
    dataset = generate(params)
    manifest = export_dataset(dataset, params, out_dir, formats, command)
    print(f"Generated {sum(manifest['row_counts'].values()):,} rows in {time.time() - started:.1f}s -> {out_dir}")
    for table, count in manifest["row_counts"].items():
        print(f"  {table:<26}{count:>9,}")
    print(f"  ground truth labels: {manifest['ground_truth_rows']}  eligible-but-unissued: {dataset.meta['pending_eligible_not_issued']}")
    if args.validate:
        if "csv" not in formats:
            sys.exit("--validate requires the csv format")
        report = validate_dataset(str(out_dir))
        (out_dir / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        header = f"Dataset: seed {params.seed}, command `{command}`."
        (out_dir / "validation_report.md").write_text(render_markdown(report, header), encoding="utf-8")
        s = report["summary"]
        print(f"Validation: {s['passed']}/{s['checks']} checks passed, {s['failed']} failed")
        for c in report["checks"]:
            if c["status"] == "FAIL":
                print(f"  FAIL {c['name']}: unexpected={c['unexpected_violations']} {c['unexpected_samples']} "
                      f"missed={c['labelled_but_not_found']} {c['missed_samples']}")
    if args.check_reproducibility:
        result = reproducibility_check(params, formats, out_dir, command)
        print(f"Reproducibility: identical across 2 regenerations = {result['identical_to_primary_output']} "
              f"({result['files_compared']} files compared)")
        if not result["identical_to_primary_output"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
