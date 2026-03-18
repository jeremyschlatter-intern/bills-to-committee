#!/usr/bin/env python3
"""
Collect bill data from congress.gov API for committee referral prediction.
Gathers bills from congresses 113-118 with their committee referrals,
policy areas, legislative subjects, and sponsor info.
"""

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = "CONGRESS_API_KEY"
BASE_URL = "https://api.congress.gov/v3"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Rate limiting
REQUEST_DELAY = 0.15  # seconds between requests


def api_get(url):
    """Make an API request with rate limiting and retries."""
    if "api_key" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={API_KEY}&format=json"
    elif "format=json" not in url:
        url = f"{url}&format=json"

    for attempt in range(3):
        try:
            time.sleep(REQUEST_DELAY)
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {e.code} for {url}")
                if attempt == 2:
                    return None
        except Exception as e:
            print(f"  Error: {e}")
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def collect_bills_list(congress, bill_type="hr", limit=250):
    """Get list of all bills for a congress."""
    bills = []
    offset = 0
    while True:
        url = f"{BASE_URL}/bill/{congress}/{bill_type}?limit={limit}&offset={offset}"
        data = api_get(url)
        if not data or "bills" not in data:
            break
        batch = data["bills"]
        if not batch:
            break
        bills.extend(batch)
        offset += limit
        print(f"  Congress {congress} {bill_type}: {len(bills)} bills...")
        if "pagination" not in data or "next" not in data["pagination"]:
            break
    return bills


def collect_bill_details(congress, bill_type, number):
    """Get detailed info for a single bill including committees and subjects."""
    # Bill detail
    detail_url = f"{BASE_URL}/bill/{congress}/{bill_type}/{number}"
    detail = api_get(detail_url)
    if not detail or "bill" not in detail:
        return None

    bill = detail["bill"]
    result = {
        "congress": congress,
        "type": bill_type,
        "number": number,
        "title": bill.get("title", ""),
        "introducedDate": bill.get("introducedDate", ""),
        "originChamber": bill.get("originChamber", ""),
        "policyArea": bill.get("policyArea", {}).get("name", ""),
        "sponsors": [],
    }

    # Sponsors
    for s in bill.get("sponsors", []):
        result["sponsors"].append({
            "name": s.get("fullName", ""),
            "party": s.get("party", ""),
            "state": s.get("state", ""),
        })

    # Committees
    comm_url = f"{detail_url}/committees"
    comm_data = api_get(comm_url)
    result["committees"] = []
    if comm_data and "committees" in comm_data:
        for c in comm_data["committees"]:
            activities = [a.get("name", "") for a in c.get("activities", [])]
            result["committees"].append({
                "name": c.get("name", ""),
                "chamber": c.get("chamber", ""),
                "systemCode": c.get("systemCode", ""),
                "activities": activities,
            })

    # Subjects
    subj_url = f"{detail_url}/subjects"
    subj_data = api_get(subj_url)
    result["legislativeSubjects"] = []
    if subj_data and "subjects" in subj_data:
        subjs = subj_data["subjects"]
        if "legislativeSubjects" in subjs:
            result["legislativeSubjects"] = [
                s.get("name", "") for s in subjs["legislativeSubjects"]
            ]
        if "policyArea" in subjs and not result["policyArea"]:
            result["policyArea"] = subjs["policyArea"].get("name", "")

    return result


def main():
    # Collect for congresses 113-118 (2013-2024), both House and Senate bills
    congresses = [113, 114, 115, 116, 117, 118]
    bill_types = ["hr", "s"]  # House and Senate bills

    for congress in congresses:
        for bill_type in bill_types:
            output_file = DATA_DIR / f"bills_{congress}_{bill_type}.json"
            if output_file.exists():
                print(f"Skipping {congress} {bill_type} - already collected")
                continue

            print(f"\nCollecting congress {congress} {bill_type}...")
            bills_list = collect_bills_list(congress, bill_type)
            print(f"  Found {len(bills_list)} bills")

            # Collect details for a sample (first 500 per congress/type to stay reasonable)
            detailed_bills = []
            max_bills = 500
            for i, bill in enumerate(bills_list[:max_bills]):
                number = bill.get("number", "")
                if not number:
                    continue
                print(f"  [{i+1}/{min(len(bills_list), max_bills)}] {bill_type.upper()} {number}...")
                detail = collect_bill_details(congress, bill_type, number)
                if detail:
                    detailed_bills.append(detail)

                # Save periodically
                if (i + 1) % 100 == 0:
                    with open(output_file, "w") as f:
                        json.dump(detailed_bills, f, indent=1)
                    print(f"  Saved {len(detailed_bills)} bills")

            # Final save
            with open(output_file, "w") as f:
                json.dump(detailed_bills, f, indent=1)
            print(f"Saved {len(detailed_bills)} bills to {output_file}")


if __name__ == "__main__":
    main()
