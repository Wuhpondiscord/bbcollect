"""Export all selected directory summaries. Requires only `pip install requests`."""
import argparse
import csv
import json
from pathlib import Path
import time

import requests


def get_json(client, url, params):
    for attempt in range(5):
        response = client.get(url, params=params, timeout=180)
        if response.status_code in (429, 503) and attempt < 4:
            retry = response.headers.get("Retry-After", "")
            delay = min(int(retry), 60) if retry.isdigit() else min(2 ** (attempt + 1), 30)
            time.sleep(delay)
            continue
        response.raise_for_status()
        data = response.json()
        if not data.get("ok") or data.get("partial"):
            raise RuntimeError("Incomplete directory response; inspect source status: " + json.dumps(data.get("sources")))
        return data
    raise RuntimeError("Retry limit reached")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://wuhp-bbconnectapi.hf.space/api/v1")
    parser.add_argument("--platforms", default="hackerone,bugcrowd,intigriti,yeswehack")
    parser.add_argument("--output", type=Path, default=Path("programs.json"))
    parser.add_argument("--csv", type=Path, help="Optional CSV of summary columns")
    args = parser.parse_args()
    programs, seen_offsets = {}, set()
    offset = 0
    with requests.Session() as client:
        while True:
            if offset in seen_offsets:
                raise RuntimeError("Repeated pagination offset")
            seen_offsets.add(offset)
            page = get_json(client, args.base_url.rstrip("/") + "/programs", {
                "platforms": args.platforms, "limit": 100, "offset": offset})
            programs.update({p["id"]: p for p in page["programs"]})
            offset = page["next_offset"]
            if offset is None:
                break
    rows = list(programs.values())
    args.output.write_text(json.dumps({"count": len(rows), "programs": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv:
        columns = ["id", "platform", "handle", "name", "url", "offers_bounties", "min_bounty", "max_bounty", "currency"]
        with args.csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Exported {len(rows)} programs to {args.output}")


if __name__ == "__main__":
    main()
