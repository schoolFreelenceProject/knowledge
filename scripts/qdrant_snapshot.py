import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Create, list, download, or recover Qdrant collection snapshots."
    )
    parser.add_argument(
        "action",
        choices=("create", "list", "download", "recover"),
        help="Snapshot operation.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=settings.qdrant_url,
        help="Qdrant HTTP URL.",
    )
    parser.add_argument(
        "--collection-name",
        default=settings.qdrant_collection_name,
        help="Qdrant collection name.",
    )
    parser.add_argument(
        "--snapshot-name",
        help="Snapshot name for download/recover.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "backups" / "qdrant",
        help="Directory for downloaded snapshots.",
    )
    parser.add_argument(
        "--location",
        help=(
            "Recover source location visible to Qdrant. This can be a URL or a "
            "server-side path mounted into the Qdrant container."
        ),
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        base_url = args.qdrant_url.rstrip("/")
        if args.action == "create":
            snapshot = _request_json(
                method="POST",
                url=_collection_url(base_url, args.collection_name, "snapshots"),
            )
            print(json.dumps(snapshot, indent=2))
            return 0

        if args.action == "list":
            snapshots = _request_json(
                method="GET",
                url=_collection_url(base_url, args.collection_name, "snapshots"),
            )
            print(json.dumps(snapshots, indent=2))
            return 0

        if args.action == "download":
            if not args.snapshot_name:
                raise ValueError("--snapshot-name is required for download.")

            args.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = args.output_dir / args.snapshot_name
            _download(
                url=_collection_url(
                    base_url,
                    args.collection_name,
                    "snapshots",
                    args.snapshot_name,
                ),
                output_path=output_path,
            )
            print(f"Qdrant snapshot downloaded to: {output_path}")
            return 0

        if args.action == "recover":
            location = args.location
            if location is None:
                if not args.snapshot_name:
                    raise ValueError(
                        "--snapshot-name or --location is required for recover."
                    )
                location = args.snapshot_name

            response = _request_json(
                method="PUT",
                url=_collection_url(
                    base_url,
                    args.collection_name,
                    "snapshots",
                    "recover",
                ),
                payload={"location": location},
            )
            print(json.dumps(response, indent=2))
            return 0

        raise ValueError(f"Unsupported action: {args.action}")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _collection_url(base_url: str, collection_name: str, *parts: str) -> str:
    encoded_collection = urllib.parse.quote(collection_name, safe="")
    encoded_parts = "/".join(urllib.parse.quote(part, safe="") for part in parts)
    return f"{base_url}/collections/{encoded_collection}/{encoded_parts}"


def _request_json(
    method: str,
    url: str,
    payload: dict | None = None,
) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        method=method,
        data=data,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, output_path: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response:
        output_path.write_bytes(response.read())


if __name__ == "__main__":
    raise SystemExit(main())
