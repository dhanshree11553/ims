#!/usr/bin/env python3
"""POST sample signals to IMS ingestion API (stdlib only; requires backend running)."""
import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000", help="Backend base URL")
    p.add_argument(
        "--file",
        type=Path,
        default=Path(__file__).resolve().parent / "sample_stack_failure.json",
    )
    p.add_argument("--repeat", type=int, default=1, help="Repeat burst per signal (stress debounce)")
    args = p.parse_args()
    data = json.loads(args.file.read_text(encoding="utf-8"))
    signals = data.get("signals", [])
    if not signals:
        print("No signals in file", file=sys.stderr)
        sys.exit(1)
    base = args.base.rstrip("/")
    for _ in range(args.repeat):
        for s in signals:
            body = json.dumps(s).encode("utf-8")
            req = urllib.request.Request(
                f"{base}/ingest/signals",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    if resp.status >= 400:
                        print(resp.status, file=sys.stderr)
                        sys.exit(1)
            except urllib.error.HTTPError as e:
                print(e.code, e.read().decode(), file=sys.stderr)
                sys.exit(1)
            print("ok", s.get("component_id"))
    print("Done.")


if __name__ == "__main__":
    main()
