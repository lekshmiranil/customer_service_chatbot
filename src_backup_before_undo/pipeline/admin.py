import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline.access_control import authorize
from src.pipeline.ingestion import RAW_DATA_DIR, VERSIONS_DIR, load_manifest, rollback_version
from src.pipeline.metrics import summarize

ACTIVE_DB_PATH = "faiss_index"


def deny():
    print("Access denied.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Knowledge base pipeline admin")
    parser.add_argument("command", choices=["run", "rollback", "status", "add-doc", "report"])
    parser.add_argument("target", nargs="?", help="version number (rollback) or file path (add-doc)")
    parser.add_argument("--token", default=None, help="access token (defaults to PIPELINE_TOKEN)")
    parser.add_argument("--hours", type=float, default=None, help="restrict report to the last N hours (default: all time)")
    args = parser.parse_args()

    if args.command == "run":
        # Imported here so denied/status commands stay fast
        from src.pipeline.scheduler import execute_pipeline_update_with_retries
        # The update function performs its own authorization check
        ok = execute_pipeline_update_with_retries(token=args.token)
        sys.exit(0 if ok else 1)

    elif args.command == "rollback":
        if not authorize(args.token, "rollback"):
            deny()
        if not args.target or not args.target.isdigit():
            print("Usage: admin.py rollback <version_number>")
            sys.exit(2)
        sys.exit(0 if rollback_version(int(args.target), ACTIVE_DB_PATH) else 1)

    elif args.command == "status":
        if not authorize(args.token, "view_status"):
            deny()
        manifest = load_manifest()
        snapshots = sorted(p.name for p in VERSIONS_DIR.glob("v*")) if VERSIONS_DIR.exists() else []
        print(f"Current version: {manifest.get('version', 0)}")
        print(f"Tracked documents: {len(manifest.get('documents', {}))}")
        print(f"Snapshots available: {len(snapshots)}")

    elif args.command == "add-doc":
        if not authorize(args.token, "add_document"):
            deny()
        if not args.target or not Path(args.target).is_file():
            print("Usage: admin.py add-doc <path_to_file>")
            sys.exit(2)
        shutil.copy2(args.target, RAW_DATA_DIR / Path(args.target).name)
        print(f"Added {Path(args.target).name} to the raw documents folder.")

    elif args.command == "report":
        if not authorize(args.token, "view_status"):
            deny()
        print(json.dumps(summarize(hours=args.hours), indent=2))


if __name__ == "__main__":
    main()