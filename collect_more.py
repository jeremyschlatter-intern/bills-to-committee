#!/usr/bin/env python3
"""
Collect more training data. Load existing data and add more bills
from different congresses, focusing on variety of policy areas.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from collections import Counter

API_KEY = "CONGRESS_API_KEY"
BASE_URL = "https://api.congress.gov/v3"
DATA_DIR = Path("data")

last_request_time = 0
MIN_DELAY = 0.1
request_count = 0


def api_get(url):
    global last_request_time, request_count
    if "api_key" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={API_KEY}&format=json"
    elif "format=json" not in url:
        url = f"{url}&format=json"

    elapsed = time.time() - last_request_time
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)

    for attempt in range(3):
        try:
            last_request_time = time.time()
            request_count += 1
            req = urllib.request.Request(url, headers={"User-Agent": "BillsToCommittee/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** attempt * 5)
            elif attempt == 2:
                return None
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def get_bill_detail(congress, bill_type, number):
    base = f"{BASE_URL}/bill/{congress}/{bill_type}/{number}"
    detail = api_get(base)
    if not detail or "bill" not in detail:
        return None
    b = detail["bill"]

    result = {
        "congress": congress,
        "type": bill_type.upper(),
        "number": int(number),
        "title": b.get("title", ""),
        "policyArea": b.get("policyArea", {}).get("name", "") if b.get("policyArea") else "",
        "originChamber": b.get("originChamber", ""),
        "sponsors": [{"party": s.get("party", ""), "state": s.get("state", "")} for s in b.get("sponsors", [])],
    }

    # Committees
    comm_data = api_get(f"{base}/committees")
    result["committees"] = []
    if comm_data and "committees" in comm_data:
        for c in comm_data["committees"]:
            result["committees"].append({
                "name": c.get("name", ""),
                "chamber": c.get("chamber", ""),
                "systemCode": c.get("systemCode", ""),
            })

    # Subjects
    subj_data = api_get(f"{base}/subjects")
    result["subjects"] = []
    if subj_data and "subjects" in subj_data:
        subjs = subj_data["subjects"]
        if "legislativeSubjects" in subjs:
            result["subjects"] = [s.get("name", "") for s in subjs["legislativeSubjects"]]
        if "policyArea" in subjs and not result["policyArea"]:
            result["policyArea"] = subjs["policyArea"].get("name", "")

    return result


def main():
    # Load existing data
    existing_file = DATA_DIR / "training_data.json"
    if existing_file.exists():
        with open(existing_file) as f:
            existing = json.load(f)
        print(f"Existing: {len(existing)} bills")
    else:
        existing = []

    # Track what we have
    existing_keys = set()
    for b in existing:
        existing_keys.add(f"{b['congress']}_{b['type']}_{b['number']}")

    # Collect from different offsets to get more variety
    new_bills = []
    configs = [
        # Congress, type, offset, count - sample from different parts of each congress
        (118, "hr", 2000, 300),
        (118, "hr", 5000, 300),
        (118, "s", 2000, 200),
        (117, "hr", 2000, 300),
        (117, "hr", 5000, 300),
        (117, "s", 2000, 200),
        (116, "hr", 2000, 300),
        (116, "s", 1000, 200),
        (115, "hr", 1000, 200),
        (115, "s", 1000, 200),
        (119, "hr", 0, 250),  # Current congress!
        (119, "s", 0, 250),
    ]

    for congress, bill_type, offset, count in configs:
        print(f"\nFetching {congress} {bill_type} offset={offset} count={count}...")
        url = f"{BASE_URL}/bill/{congress}/{bill_type}?limit=250&offset={offset}"
        data = api_get(url)
        if not data or "bills" not in data:
            print("  No data")
            continue

        bills = data["bills"]
        # Get more pages if needed
        while len(bills) < count and "pagination" in data and "next" in data.get("pagination", {}):
            data = api_get(data["pagination"]["next"])
            if not data or "bills" not in data:
                break
            bills.extend(data["bills"])

        print(f"  Got {len(bills)} bill numbers")

        for i, bill in enumerate(bills[:count]):
            number = bill.get("number", "")
            key = f"{congress}_{bill_type.upper()}_{number}"
            if key in existing_keys:
                continue

            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{min(len(bills), count)}]...")

            detail = get_bill_detail(congress, bill_type, number)
            if detail and detail["committees"]:
                new_bills.append(detail)
                existing_keys.add(key)

    print(f"\nCollected {len(new_bills)} new bills ({request_count} API requests)")

    # Merge with existing
    all_bills = existing + new_bills
    with open(existing_file, "w") as f:
        json.dump(all_bills, f, indent=1)
    print(f"Total training data: {len(all_bills)} bills")

    # Stats
    pa_counts = Counter(b.get("policyArea", "") for b in all_bills if b.get("policyArea"))
    comm_counts = Counter()
    for b in all_bills:
        for c in b.get("committees", []):
            comm_counts[c["name"]] += 1

    print(f"\nPolicy areas: {len(pa_counts)}")
    for pa, count in pa_counts.most_common(10):
        print(f"  {pa}: {count}")
    print(f"\nCommittees: {len(comm_counts)}")
    for name, count in comm_counts.most_common(10):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
