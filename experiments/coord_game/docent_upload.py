"""Upload saved rollouts to a Docent collection. No model calls.

    uv run python -m experiments.coord_game.docent_upload reports/coord-game/<run> --collection coord-game

Collections are private unless --public is passed. After a successful upload, a
receipt (docent_upload.json) is written in the run folder; a run with a receipt
for the same collection is skipped, so re-running is safe. Each run also carries
a stable export_key in its Docent metadata. Needs DOCENT_API_KEY in .env or the shell.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ai_collusion.docent_cli import make_client, resolve_collection_id
from ai_collusion.run_storage import write_json

from .docent import rollout_to_agent_run
from .game import load_rollout

RECEIPT = "docent_upload.json"


def _folder(path):
    path = Path(path).expanduser().resolve()
    return path if path.is_dir() else path.parent


def _receipts(folder):
    path = folder / RECEIPT
    return json.loads(path.read_text()) if path.exists() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("runs", nargs="+", type=Path, help="rollout folders or rollout.json files")
    parser.add_argument("--collection", required=True, help="collection name (created if missing)")
    parser.add_argument("--public", action="store_true", help="make the collection publicly readable")
    args = parser.parse_args(argv)

    folders = [_folder(path) for path in args.runs]
    runs = [rollout_to_agent_run(load_rollout(folder)) for folder in folders]  # validate all first
    client = make_client()
    collection_id = resolve_collection_id(client, args.collection)
    uploaded = 0
    for folder, run in zip(folders, runs):
        receipts = _receipts(folder)
        if any(r["collection_id"] == collection_id for r in receipts):
            print(f"skip (receipt found): {run.name}")
            continue
        client.add_agent_runs(collection_id, [run])
        receipts.append({"collection_id": collection_id, "collection_name": args.collection,
                         "agent_run_id": run.id, "export_key": run.metadata["export_key"],
                         "uploaded_utc": datetime.now(timezone.utc).isoformat()})
        write_json(folder / RECEIPT, receipts)
        uploaded += 1
        print(f"uploaded: {run.name}")
    if args.public:
        client.share_collection_with_public(collection_id, permission="read")
        print("Collection is now publicly readable.")
    print(f"Collection {args.collection!r} ({collection_id}): {uploaded} uploaded, "
          f"{len(runs) - uploaded} skipped. {'Public.' if args.public else 'Private unless shared.'}")


if __name__ == "__main__":
    main()
