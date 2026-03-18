#!/usr/bin/env python3
"""
Smart data collection strategy:
1. Use bill list endpoint (250 bills per request) - latestAction often contains committee referral
2. Use bill detail endpoint selectively for policy area and subjects
3. Much faster than fetching full details for every bill
"""

import json
import time
import re
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = "CONGRESS_API_KEY"
BASE_URL = "https://api.congress.gov/v3"
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

last_request_time = 0
MIN_DELAY = 0.1
request_count = 0


def api_get(url):
    """Make an API request with rate limiting."""
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
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  HTTP {e.code}")
                if attempt == 2:
                    return None
        except Exception as e:
            if attempt == 2:
                return None
            time.sleep(2)
    return None


def extract_committee_from_action(action_text):
    """Extract committee name from action text like 'Referred to the House Committee on X'."""
    if not action_text:
        return []

    committees = []
    # Common patterns
    patterns = [
        r"Referred to the (House Committee on .+?)(?:\.|$)",
        r"Referred to the (Committee on .+?)(?:\.|$)",
        r"Referred to the (Senate Committee on .+?)(?:\.|$)",
        r"Read twice and referred to the (Committee on .+?)(?:\.|$)",
        r"Referred to the (Subcommittee on .+?)(?:\.|$)",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, action_text)
        committees.extend(matches)

    return committees


def collect_all_bills_fast(congress, bill_type, max_pages=20):
    """Collect bill list data (250 per page). Very fast."""
    all_bills = []
    offset = 0
    limit = 250

    for page in range(max_pages):
        url = f"{BASE_URL}/bill/{congress}/{bill_type}?limit={limit}&offset={offset}"
        data = api_get(url)
        if not data or "bills" not in data:
            break

        bills = data["bills"]
        if not bills:
            break

        for b in bills:
            action_text = b.get("latestAction", {}).get("text", "")
            committees = extract_committee_from_action(action_text)
            all_bills.append({
                "congress": congress,
                "type": bill_type.upper(),
                "number": b.get("number", ""),
                "title": b.get("title", ""),
                "originChamber": b.get("originChamber", ""),
                "actionText": action_text,
                "committees_from_action": committees,
            })

        offset += limit
        print(f"  {congress} {bill_type}: {len(all_bills)} bills (page {page+1})...")

        if "pagination" not in data or "next" not in data.get("pagination", {}):
            break

    return all_bills


def enrich_bills_with_details(bills, sample_size=200):
    """Add policyArea and subjects to a sample of bills."""
    # Prioritize bills where we found committee referrals
    with_committees = [b for b in bills if b.get("committees_from_action")]
    without = [b for b in bills if not b.get("committees_from_action")]

    # Take all with committees, plus some without
    sample = with_committees[:sample_size]
    remaining = sample_size - len(sample)
    if remaining > 0:
        sample.extend(without[:remaining])

    enriched = []
    for i, bill in enumerate(sample):
        if (i + 1) % 50 == 0:
            print(f"  Enriching [{i+1}/{len(sample)}]...")

        congress = bill["congress"]
        bill_type = bill["type"].lower()
        number = bill["number"]

        # Get detail for policyArea + committees + subjects
        detail_url = f"{BASE_URL}/bill/{congress}/{bill_type}/{number}"
        detail = api_get(detail_url)

        if detail and "bill" in detail:
            b = detail["bill"]
            bill["policyArea"] = b.get("policyArea", {}).get("name", "") if b.get("policyArea") else ""
            bill["sponsors"] = [
                {"party": s.get("party", ""), "state": s.get("state", "")}
                for s in b.get("sponsors", [])
            ]

            # Get actual committee assignments
            comm_data = api_get(f"{detail_url}/committees")
            bill["committees"] = []
            if comm_data and "committees" in comm_data:
                for c in comm_data["committees"]:
                    bill["committees"].append({
                        "name": c.get("name", ""),
                        "chamber": c.get("chamber", ""),
                        "systemCode": c.get("systemCode", ""),
                    })

            # Get subjects
            subj_data = api_get(f"{detail_url}/subjects")
            bill["subjects"] = []
            if subj_data and "subjects" in subj_data:
                subjs = subj_data["subjects"]
                if "legislativeSubjects" in subjs:
                    bill["subjects"] = [s.get("name", "") for s in subjs["legislativeSubjects"]]
                if "policyArea" in subjs and not bill.get("policyArea"):
                    bill["policyArea"] = subjs["policyArea"].get("name", "")

            enriched.append(bill)

    return enriched


def main():
    print("Phase 1: Collecting bill lists (fast)...")
    all_bills = []

    # Collect from congresses 114-118
    for congress in [118, 117, 116, 115, 114]:
        for bill_type in ["hr", "s"]:
            print(f"\nCongress {congress} {bill_type}:")
            bills = collect_all_bills_fast(congress, bill_type, max_pages=8)
            all_bills.extend(bills)

    print(f"\nPhase 1 complete: {len(all_bills)} total bills, {request_count} API requests")

    # Save raw list data
    with open(DATA_DIR / "bills_list_raw.json", "w") as f:
        json.dump(all_bills, f, indent=1)

    # Count how many have committee referrals from action text
    with_comm = sum(1 for b in all_bills if b.get("committees_from_action"))
    print(f"Bills with committee info from action text: {with_comm}")

    print("\nPhase 2: Enriching sample with full details...")
    # Enrich 300 bills from each chamber
    house_bills = [b for b in all_bills if b["originChamber"] == "House"]
    senate_bills = [b for b in all_bills if b["originChamber"] == "Senate"]

    enriched = []
    print(f"\nEnriching House bills ({len(house_bills)} available):")
    enriched.extend(enrich_bills_with_details(house_bills, 400))
    print(f"\nEnriching Senate bills ({len(senate_bills)} available):")
    enriched.extend(enrich_bills_with_details(senate_bills, 300))

    # Save enriched data
    with open(DATA_DIR / "training_data.json", "w") as f:
        json.dump(enriched, f, indent=1)

    print(f"\nPhase 2 complete: {len(enriched)} enriched bills, {request_count} total API requests")

    # Print stats
    from collections import Counter
    policy_areas = Counter(b.get("policyArea", "") for b in enriched if b.get("policyArea"))
    committees = Counter()
    for b in enriched:
        for c in b.get("committees", []):
            committees[c["name"]] += 1

    print(f"\nPolicy areas ({len(policy_areas)}):")
    for pa, count in policy_areas.most_common(20):
        print(f"  {pa}: {count}")

    print(f"\nTop committees ({len(committees)}):")
    for name, count in committees.most_common(25):
        print(f"  {name}: {count}")


if __name__ == "__main__":
    main()
