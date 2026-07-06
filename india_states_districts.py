"""
Fetches all Indian states and districts from a reliable GitHub source
(sab99r/Indian-States-And-Districts) and writes them to a CSV file.

Output: india_states_districts.csv
"""

import csv
import json
import ssl
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/sab99r/"
    "Indian-States-And-Districts/master/states-and-districts.json"
)
OUTPUT_FILE = Path("india_states_districts.csv")


def fetch_data(url: str) -> list[dict]:
    print(f"Fetching data from:\n  {url}\n")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=15) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"ERROR: Failed to fetch data — {exc}", file=sys.stderr)
        sys.exit(1)

    states = raw.get("states", [])
    if not states:
        print("ERROR: Unexpected data format — 'states' key missing.", file=sys.stderr)
        sys.exit(1)
    return states


def write_csv(states: list[dict], output: Path) -> None:
    rows = []
    for state_obj in states:
        state = state_obj.get("state", "").strip()
        districts = state_obj.get("districts", [])
        for idx, district in enumerate(districts, start=1):
            rows.append({
                "State / UT": state,
                "District No.": idx,
                "District Name": district.strip(),
            })

    with output.open("w", newline="", encoding="utf-8-sig") as f:
        # utf-8-sig adds BOM so Excel opens it correctly without garbled text
        writer = csv.DictWriter(
            f,
            fieldnames=["State / UT", "District No.", "District Name"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()

        current_state = None
        for row in rows:
            # Insert a blank separator row between states for readability
            if current_state and current_state != row["State / UT"]:
                writer.writerow({"State / UT": "", "District No.": "", "District Name": ""})
            writer.writerow(row)
            current_state = row["State / UT"]

    return rows


def print_summary(states: list[dict]) -> None:
    total_districts = sum(len(s.get("districts", [])) for s in states)
    print(f"{'State / UT':<40} {'Districts':>10}")
    print("-" * 52)
    for s in sorted(states, key=lambda x: x["state"]):
        name = s["state"]
        count = len(s.get("districts", []))
        print(f"  {name:<38} {count:>10}")
    print("-" * 52)
    print(f"  {'TOTAL — ' + str(len(states)) + ' States/UTs':<38} {total_districts:>10}")


def main() -> None:
    states = fetch_data(SOURCE_URL)
    rows = write_csv(states, OUTPUT_FILE)

    print_summary(states)
    print(f"\nCSV saved to: {OUTPUT_FILE.resolve()}")
    print(f"Total rows written: {len(rows)} (excluding blank separator rows)")


if __name__ == "__main__":
    main()
