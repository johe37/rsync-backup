#!/usr/bin/env python3
"""
rsync-grace — rsync backup with grace-period deletion of files missing from source.
"""

import os
import sys
import fcntl
import logging
import argparse
import subprocess
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Set, List

LOG_DIR = Path("/var/log/rsync_backup")
STATE_DIR = Path("/var/lib/rsync_backup")


def setup_logging(log_file: Path) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
    )


def sanitize(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lstrip("/"))


def acquire_lock(lock_file: Path):
    """Return an open file handle that holds an exclusive lock, or exit."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_file, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logging.error(f"Another instance for {lock_file.stem} is already running.")
        sys.exit(1)
    return fh  # keep the handle open to hold the lock


def collect_paths(root: Path) -> Set[str]:
    """Return a set of all relative paths under root."""
    paths = set()
    for p in root.rglob("*"):
        rel = str(p.relative_to(root))
        paths.add(rel)
    return paths


def run_rsync(src: Path, dest: Path, dry_run: bool, excludes: List[str]) -> None:
    cmd = ["rsync", "-avh"]
    if dry_run:
        cmd.append("--dry-run")
    for pattern in excludes:
        cmd.extend(["--exclude", pattern])
    cmd += [f"{src}/", f"{dest}/"]

    logging.info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)  # live output
    if result.returncode != 0:
        logging.error(f"rsync failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def load_state(state_file: Path) -> Dict[str, str]:
    """Load missing-since dates. Format: date<TAB>rel_path"""
    state = {}
    if state_file.exists():
        for line in state_file.read_text().splitlines():
            if "\t" in line:
                date, path = line.split("\t", 1)
                state[path] = date
    return state


def save_state(state_file: Path, state: Dict[str, str]) -> None:
    lines = [f"{date}\t{path}" for path, date in sorted(state.items(), key=lambda x: x[0])]
    state_file.write_text("\n".join(lines) + ("\n" if lines else ""))


def process_deletions(
    src_paths: Set[str],
    dest: Path,
    state: Dict[str, str],
    grace_days: int,
    dry_run: bool,
) -> Dict[str, str]:
    today = datetime.now().date()
    cutoff = today - timedelta(days=grace_days)
    new_state = {}

    dest_paths = collect_paths(dest)

    for rel in sorted(dest_paths):
        if rel in src_paths:
            # Restored – drop from state
            if rel in state:
                logging.info(f"Restored in source (removed from deletion queue): {rel}")
            continue

        # Still missing
        first_seen = state.get(rel, today.isoformat())
        first_date = datetime.fromisoformat(first_seen).date()

        if first_date <= cutoff:
            target = dest / rel
            if target.exists() or target.is_symlink():
                if dry_run:
                    logging.info(f"[DRY-RUN] Would delete (missing ≥ {grace_days}d, since {first_seen}): {rel}")
                    new_state[rel] = first_seen  # keep tracking in dry-run
                else:
                    logging.info(f"Deleting (missing ≥ {grace_days}d, since {first_seen}): {rel}")
                    if target.is_dir() and not target.is_symlink():
                        shutil.rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
        else:
            # Still in grace period
            if rel not in state:
                logging.info(f"Marked as missing in source (since {first_seen}): {rel}")
            new_state[rel] = first_seen

    return new_state


def show_status(pair_id: str | None = None) -> None:
    """Show a compact status of the latest run for each backup pair."""
    if not LOG_DIR.exists():
        print("No backup logs found.")
        return

    logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not logs:
        print("No matching backup logs found.")
        return

    # Keep only the newest log per pair
    latest = {}
    for log_file in logs:
        name = log_file.stem  # e.g. 2026-11-21_03-00-01_home_johe-to-...

        # Timestamp is the first two parts: YYYY-MM-DD_HH-MM-SS
        parts = name.split("_", 2)
        if len(parts) >= 3:
            pair = parts[2]
        else:
            pair = name

        if pair_id and not pair.startswith(pair_id):
            continue

        if pair not in latest:
            latest[pair] = log_file

    if not latest:
        print("No matching backup logs found.")
        return

    print("Backup status:")
    print("─" * 72)

    for pair, log_file in sorted(latest.items()):
        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        age = datetime.now() - mtime
        if age.days:
            age_str = f"{age.days}d {age.seconds // 3600}h ago"
        else:
            age_str = f"{age.seconds // 3600}h {(age.seconds % 3600) // 60}m ago"

        try:
            content = log_file.read_text()
            if "Backup completed successfully" in content:
                status = "OK"
            elif "Dry-run completed successfully" in content:
                status = "DRY-RUN"
            elif "FAILED" in content or "failed" in content:
                status = "FAILED"
            else:
                status = "UNKNOWN"
        except Exception:
            status = "ERROR"

        # Make the name shorter and nicer
        short = (pair
                 .replace("zfs_pool01_backups_", "")
                 .replace("home_", "")
                 .replace("mnt_", "")
                 .replace("var_lib_", ""))

        print(f"  {mtime.strftime('%Y-%m-%d %H:%M')}  {status:<8}  {short:<40} ({age_str})")

    print("─" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="rsync backup with grace-period deletion"
    )
    parser.add_argument("source", type=Path, nargs="?", help="Source directory")
    parser.add_argument("destination", type=Path, nargs="?", help="Destination directory")
    parser.add_argument(
        "--grace-days",
        type=int,
        default=int(os.getenv("GRACE_DAYS", "14")),
        help="Days a file must remain missing before deletion (default: 14)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("DRY_RUN") == "1",
        help="Preview changes without modifying anything",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Exclude pattern passed to rsync (can be used multiple times)",
    )
    parser.add_argument(
    "--status",
    action="store_true",
    help="Show status of the most recent backup run(s) and exit",
    )
    parser.add_argument(
        "--status-pair",
        metavar="PAIR_ID",
        help="Only show status for a specific pair id",
    )
    args = parser.parse_args()

    if args.status or args.status_pair:
        show_status(pair_id=args.status_pair)
        sys.exit(0)

    # Normal backup mode requires source + destination
    if not args.source or not args.destination:
        parser.error("source and destination are required unless --status is used")

    src = args.source.resolve()
    dest = args.destination.resolve()

    if not src.is_dir():
        print(f"Error: Source directory '{src}' does not exist.", file=sys.stderr)
        sys.exit(1)

    pair_id = f"{sanitize(str(src))}-to-{sanitize(str(dest))}"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOG_DIR / f"{timestamp}_{pair_id}.log"
    state_file = STATE_DIR / f"{pair_id}.missing.tsv"
    lock_file = STATE_DIR / f"{pair_id}.lock"

    setup_logging(log_file)
    lock_fh = acquire_lock(lock_file)

    logging.info(f"===== Backup started (GRACE_DAYS={args.grace_days}, DRY_RUN={int(args.dry_run)}) =====")
    logging.info(f"Source: {src}")
    logging.info(f"Destination: {dest}")
    if args.exclude:
        logging.info(f"Excludes: {', '.join(args.exclude)}")

    run_rsync(src, dest, args.dry_run, args.exclude)

    src_paths = collect_paths(src)
    state = load_state(state_file)
    new_state = process_deletions(src_paths, dest, state, args.grace_days, args.dry_run)

    if not args.dry_run:
        save_state(state_file, new_state)

    if args.dry_run:
        logging.info("Dry-run completed successfully (no changes were made)")
    else:
        logging.info("Backup completed successfully")
    logging.info("====================================")


if __name__ == "__main__":
    main()
