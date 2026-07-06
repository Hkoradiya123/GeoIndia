"""
Fetches all Indian states/UTs and their districts directly from the
official Government of India source:

  LGD — Local Government Directory
  Ministry of Panchayati Raj, Government of India
  https://lgdirectory.gov.in

Uses the LGD's own DWR (Direct Web Remoting) API — the same API that
powers the official web portal — so the data is authoritative and up-to-date.

Output: india_states_districts_govt.csv
"""

import csv
import http.cookiejar
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

LGD_BASE = "https://lgdirectory.gov.in"
OUTPUT_FILE = Path("india_states_districts_govt.csv")


def make_opener() -> tuple[urllib.request.OpenerDirector, http.cookiejar.CookieJar]:
    ctx = ssl.create_default_context()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(jar),
    )
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"),
        ("Accept", "text/html,*/*"),
    ]
    return opener, jar


def get_jsessionid(opener: urllib.request.OpenerDirector, jar: http.cookiejar.CookieJar) -> str:
    """Visit the portal once to acquire a JSESSIONID session cookie."""
    req = urllib.request.Request(f"{LGD_BASE}/districtWiseDetailReport.do")
    with opener.open(req, timeout=15) as r:
        r.read()
    for cookie in jar:
        if cookie.name == "JSESSIONID":
            return cookie.value
    raise RuntimeError("Could not obtain JSESSIONID from LGD portal")


def fetch_state_codes(opener: urllib.request.OpenerDirector) -> list[tuple[str, str]]:
    """Parse state codes and names from the district report form."""
    req = urllib.request.Request(f"{LGD_BASE}/districtWiseDetailReport.do")
    with opener.open(req, timeout=15) as r:
        html = r.read().decode("utf-8", errors="replace")

    options = re.findall(
        r'<option[^>]*value=["\'](\d+)["\'][^>]*>(.*?)</option>',
        html, re.IGNORECASE
    )
    states = [(code.strip(), label.strip()) for code, label in options if code.strip()]
    if not states:
        raise RuntimeError("Could not parse state codes from LGD portal")
    return states


def fetch_districts(
    opener: urllib.request.OpenerDirector,
    jsessionid: str,
    state_code: str,
    state_name: str,
) -> list[str]:
    """
    Call the LGD DWR API to get the district list for a state.
    Returns a list of district name strings.
    """
    dwr_body = (
        "callCount=1\n"
        "nextReverseAjaxIndex=0\n"
        "c0-scriptName=lgdDwrDistrictService\n"
        "c0-methodName=getDistrictList\n"
        "c0-id=0\n"
        f"c0-param0=number:{state_code}\n"
        "batchId=1\n"
        "instanceId=0\n"
        "page=%2FdistrictWiseDetailReport.do\n"
        f"httpSessionId={jsessionid}\n"
        f"scriptSessionId={jsessionid}00\n"
    )
    req = urllib.request.Request(
        f"{LGD_BASE}/dwr/call/plaincall/lgdDwrDistrictService.getDistrictList.dwr",
        data=dwr_body.encode("utf-8"),
        headers={
            "Content-Type": "text/plain",
            "Origin": LGD_BASE,
            "Referer": f"{LGD_BASE}/districtWiseDetailReport.do",
        },
    )
    with opener.open(req, timeout=15) as r:
        resp = r.read().decode("utf-8", errors="replace")

    # Extract districtNameEnglish values from DWR response
    names = re.findall(r'districtNameEnglish:"(.*?)"', resp)
    if not names:
        print(f"  WARNING: No districts found for {state_name} (code {state_code})")
    return [n.strip() for n in names]


def write_csv(data: list[tuple[str, list[str]]], output: Path) -> int:
    total = 0
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["State / UT", "LGD State Code", "District No.", "District Name"],
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        first = True
        for state_name, state_code, districts in data:
            if not first:
                writer.writerow({
                    "State / UT": "", "LGD State Code": "",
                    "District No.": "", "District Name": ""
                })
            first = False
            for idx, district in enumerate(sorted(districts), start=1):
                writer.writerow({
                    "State / UT": state_name,
                    "LGD State Code": state_code,
                    "District No.": idx,
                    "District Name": district,
                })
                total += 1
    return total


def print_summary(data: list[tuple[str, str, list[str]]]) -> None:
    total = sum(len(d) for _, _, d in data)
    print(f"\n{'State / UT':<50} {'Code':>6} {'Districts':>10}")
    print("-" * 70)
    for state_name, code, districts in data:
        print(f"  {state_name:<48} {code:>6} {len(districts):>10}")
    print("-" * 70)
    print(f"  {'TOTAL — ' + str(len(data)) + ' States/UTs':<48} {'':>6} {total:>10}")
    print()


def main() -> None:
    print("Source: LGD — Local Government Directory, Government of India")
    print(f"  {LGD_BASE}\n")

    opener, jar = make_opener()

    print("Acquiring session...")
    jsessionid = get_jsessionid(opener, jar)

    print("Fetching state list...")
    state_codes = fetch_state_codes(opener)
    print(f"  Found {len(state_codes)} states/UTs\n") 
    collected: list[tuple[str, str, list[str]]] = []
    for i, (code, name) in enumerate(state_codes, start=1):
        print(f"  [{i:02d}/{len(state_codes)}] {name} (code {code})...", end=" ", flush=True)
        try:
            districts = fetch_districts(opener, jsessionid, code, name)
            print(f"{len(districts)} districts")
            collected.append((name, code, districts))
        except Exception as exc:
            print(f"ERROR — {exc}")
        time.sleep(0.3)  # polite delay between requests

    print_summary(collected)

    total_rows = write_csv(collected, OUTPUT_FILE)
    print(f"CSV saved  : {OUTPUT_FILE.resolve()}")
    print(f"Total rows : {total_rows}")


if __name__ == "__main__":
    main()
