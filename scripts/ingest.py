#!/usr/bin/env python3
"""CLI for ingesting music-gen outputs into the music-platform catalog.

Usage:
    python scripts/ingest.py scan <output_dir> [--dry-run]
    python scripts/ingest.py job <manifest_path> [--dry-run]
    python scripts/ingest.py single <job_id> --output-dir <dir> [--dry-run]

Examples:
    # Scan all jobs in music-gen output directory
    python scripts/ingest.py scan ../music-gen/data/out
    
    # Ingest a specific job
    python scripts/ingest.py job ../music-gen/data/out/abc123/manifest.json
    
    # Dry run to see what would happen
    python scripts/ingest.py scan ../music-gen/data/out --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ingest import ingest_job, scan_and_ingest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("ingest")


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan output directory and ingest all jobs."""
    stats = scan_and_ingest(args.output_dir, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2, default=str))
    return 0 if stats["failed"] == 0 else 1


def cmd_job(args: argparse.Namespace) -> int:
    """Ingest a single job from manifest."""
    results = ingest_job(Path(args.manifest), dry_run=args.dry_run)
    
    for result in results:
        status_emoji = {"ingested": "✓", "skipped": "○", "failed": "✗"}.get(result.status, "?")
        print(f"{status_emoji} {result.job_id}/{result.source_type}: {result.status}")
        if result.message:
            print(f"  {result.message}")
        if result.track_id:
            print(f"  track_id: {result.track_id}")
        if result.dest_path:
            print(f"  path: {result.dest_path}")
    
    failed = sum(1 for r in results if r.status == "failed")
    return 0 if failed == 0 else 1


def cmd_single(args: argparse.Namespace) -> int:
    """Ingest a specific job ID from output directory."""
    stats = scan_and_ingest(args.output_dir, dry_run=args.dry_run, job_id_filter=args.job_id)
    print(json.dumps(stats, indent=2, default=str))
    return 0 if stats["failed"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description="Ingest music-gen outputs into music-platform catalog",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # scan command
    scan_parser = subparsers.add_parser("scan", help="Scan output directory and ingest all jobs")
    scan_parser.add_argument("output_dir", type=Path, help="Path to music-gen output directory")
    scan_parser.set_defaults(func=cmd_scan)
    
    # job command
    job_parser = subparsers.add_parser("job", help="Ingest a single job from manifest")
    job_parser.add_argument("manifest", type=Path, help="Path to manifest.json")
    job_parser.set_defaults(func=cmd_job)
    
    # single command
    single_parser = subparsers.add_parser("single", help="Ingest a specific job ID")
    single_parser.add_argument("job_id", help="Job ID to ingest")
    single_parser.add_argument("--output-dir", type=Path, required=True, help="Base output directory")
    single_parser.set_defaults(func=cmd_single)
    
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
