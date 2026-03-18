#!/usr/bin/env python3
"""
Fast data collection - grab bill lists with basic info, then selectively
fetch committee/subject details. Optimized for speed.
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = "CONGRESS_API_KEY"
BASE_URL = "https://api.congress.gov/v3"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Track request timing for rate limiting
last_request_time = 0
MIN_DELAY = 0.12


def api_get(url):
    """Make an API request with rate limiting."""
    global last_request_time
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
            req = urllib.request.Request(url, headers={"User-Agent": "BillsToCommittee/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {e.code} for {url[:80]}")
                if attempt == 2:
                    return None
        except Exception as e:
            print(f"  Error: {e}")
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def get_bill_with_details(congress, bill_type, number):
    """Get bill detail + committees + subjects in 3 API calls."""
    base = f"{BASE_URL}/bill/{congress}/{bill_type}/{number}"

    detail = api_get(base)
    if not detail or "bill" not in detail:
        return None
    bill = detail["bill"]

    result = {
        "congress": congress,
        "type": bill_type.upper(),
        "number": int(number),
        "title": bill.get("title", ""),
        "policyArea": bill.get("policyArea", {}).get("name", "") if bill.get("policyArea") else "",
        "originChamber": bill.get("originChamber", ""),
        "sponsors": [
            {"party": s.get("party", ""), "state": s.get("state", "")}
            for s in bill.get("sponsors", [])
        ],
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


def collect_bill_numbers(congress, bill_type, max_bills=250):
    """Get bill numbers from the list endpoint."""
    url = f"{BASE_URL}/bill/{congress}/{bill_type}?limit=250&offset=0"
    data = api_get(url)
    if not data or "bills" not in data:
        return []
    bills = data["bills"]
    numbers = [b.get("number", "") for b in bills if b.get("number")]

    # Get more if available
    while len(numbers) < max_bills and "pagination" in data and "next" in data.get("pagination", {}):
        data = api_get(data["pagination"]["next"])
        if not data or "bills" not in data:
            break
        more = [b.get("number", "") for b in data["bills"] if b.get("number")]
        if not more:
            break
        numbers.extend(more)

    return numbers[:max_bills]


def main():
    # Focus on recent congresses with good data
    configs = [
        (118, "hr", 800), (118, "s", 500),
        (117, "hr", 800), (117, "s", 500),
        (116, "hr", 800), (116, "s", 500),
        (115, "hr", 600), (115, "s", 400),
        (114, "hr", 600), (114, "s", 400),
    ]

    all_bills = []
    output_file = DATA_DIR / "training_data.json"

    for congress, bill_type, max_bills in configs:
        cache_file = DATA_DIR / f"cache_{congress}_{bill_type}.json"
        if cache_file.exists():
            print(f"Loading cached {congress} {bill_type}...")
            with open(cache_file) as f:
                bills = json.load(f)
            all_bills.extend(bills)
            continue

        print(f"\nCollecting {congress} {bill_type} (up to {max_bills})...")
        numbers = collect_bill_numbers(congress, bill_type, max_bills)
        print(f"  Found {len(numbers)} bill numbers")

        bills = []
        for i, num in enumerate(numbers):
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(numbers)}] ...")
            result = get_bill_with_details(congress, bill_type, num)
            if result and result["committees"]:  # Only keep bills with committee data
                bills.append(result)

        # Cache this batch
        with open(cache_file, "w") as f:
            json.dump(bills, f, indent=1)
        print(f"  Got {len(bills)} bills with committee data")
        all_bills.extend(bills)

    # Save combined training data
    with open(output_file, "w") as f:
        json.dump(all_bills, f, indent=1)
    print(f"\nTotal: {len(all_bills)} bills saved to {output_file}")

    # Print summary stats
    from collections import Counter
    policy_areas = Counter(b["policyArea"] for b in all_bills if b["policyArea"])
    committees = Counter()
    for b in all_bills:
        for c in b["committees"]:
            committees[c["name"]] += 1

    print(f"\nPolicy areas: {len(policy_areas)}")
    for pa, count in policy_areas.most_common(15):
        print(f"  {pa}: {count}")

    print(f"\nTop committees: {len(committees)}")
    for name, count in committees.most_common(20):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
