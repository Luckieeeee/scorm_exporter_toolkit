#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "outputs"
DEFAULT_STATE_FILE = ROOT / ".scorm_exporter_watch_state.json"


def slugify(value):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_")[:100] or "course"


def prefix_from_filename(path):
    stem = path.stem
    stem = re.sub(r" \(\d+\)$", "", stem)
    stem = re.sub(r"_course$", "", stem)
    return slugify(stem)


def load_state(path):
    if not path.exists():
        return {"processed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"processed": []}
    if not isinstance(data, dict) or not isinstance(data.get("processed"), list):
        return {"processed": []}
    return data


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    state["processed"] = state["processed"][-2000:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def file_key(path):
    stat = path.stat()
    return f"{path.resolve()}::{stat.st_size}::{stat.st_mtime_ns}"


def matching_course_files(watch_dir):
    if not watch_dir.exists():
        return []
    return sorted(
        (path for path in watch_dir.glob("*_course*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )


def wait_until_stable(path, stable_seconds):
    try:
        first = path.stat()
    except FileNotFoundError:
        return False
    time.sleep(stable_seconds)
    try:
        second = path.stat()
    except FileNotFoundError:
        return False
    return first.st_size == second.st_size and first.st_mtime_ns == second.st_mtime_ns


def is_course_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("course"), dict)


def export_course(path, output_dir, mode):
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = prefix_from_filename(path)
    cmd = [
        sys.executable,
        str(ROOT / "export_scorm_course.py"),
        "--input-json",
        str(path),
        "--output-dir",
        str(output_dir),
        "--prefix",
        prefix,
        "--mode",
        mode,
    ]
    print(f"[scorm-watcher] Exporting {path.name} -> {output_dir / prefix}.*", flush=True)
    result = subprocess.run(cmd, cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Exporter failed for {path}")


def scan_once(args, state):
    processed = set(state.get("processed", []))
    changed = False
    exported = 0

    for path in matching_course_files(args.watch_dir):
        try:
            key = file_key(path)
        except FileNotFoundError:
            continue

        if key in processed and not args.reprocess:
            continue
        if not wait_until_stable(path, args.stable_seconds):
            continue
        if not is_course_json(path):
            print(f"[scorm-watcher] Skipping non-course JSON: {path.name}", flush=True)
            state.setdefault("processed", []).append(key)
            changed = True
            continue

        export_course(path, args.output_dir, args.mode)
        state.setdefault("processed", []).append(key)
        changed = True
        exported += 1

    if changed:
        save_state(args.state_file, state)
    return exported


def mark_existing(args, state):
    existing = set(state.get("processed", []))
    for path in matching_course_files(args.watch_dir):
        try:
            existing.add(file_key(path))
        except FileNotFoundError:
            continue
    state["processed"] = sorted(existing)
    save_state(args.state_file, state)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Watch a downloads folder for D2L SCORM *_course.json files and export them automatically."
    )
    parser.add_argument("--watch-dir", type=Path, default=Path.home() / "Downloads", help="Folder to watch.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Folder for generated exports.")
    parser.add_argument("--mode", choices=["plain", "styled"], default="styled", help="Export mode.")
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Seconds between scans.")
    parser.add_argument("--stable-seconds", type=float, default=1.0, help="Seconds a file must stay unchanged before export.")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE, help="Processed-file state file.")
    parser.add_argument("--once", action="store_true", help="Scan once, process matching files, then exit.")
    parser.add_argument("--process-existing", action="store_true", help="In watch mode, export matching files that already exist at startup.")
    parser.add_argument("--reprocess", action="store_true", help="Ignore the state file and re-export matching files.")
    return parser.parse_args()


def main():
    args = parse_args()
    args.watch_dir = args.watch_dir.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.state_file = args.state_file.expanduser().resolve()

    state = load_state(args.state_file)

    if not args.once and not args.process_existing and not args.reprocess:
        mark_existing(args, state)

    print(f"[scorm-watcher] Watching {args.watch_dir}", flush=True)
    print(f"[scorm-watcher] Exports will be written to {args.output_dir}", flush=True)
    print("[scorm-watcher] Press Ctrl+C to stop.", flush=True)

    if args.once:
        count = scan_once(args, state)
        print(f"[scorm-watcher] Exported {count} file(s).", flush=True)
        return

    while True:
        try:
            scan_once(args, state)
            time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            print("\n[scorm-watcher] Stopped.", flush=True)
            return


if __name__ == "__main__":
    main()
