#!/usr/bin/env python3
"""
Build a committee prediction model from training data.
Outputs a JSON model file that can be used client-side in the browser.

Model approach:
1. policyArea → committee probability distribution (strongest signal)
2. Legislative subject keywords → committee probability boosts
3. Title keyword → committee probability boosts
4. Chamber-specific committee tracking (House and Senate committees kept separate)

Includes cross-validation evaluation.
"""

import json
import re
import random
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path("data")
OUTPUT_DIR = Path("webapp/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Map historical/variant committee names to current official names
# Uses the "Committee on X" format per House Rule X and Senate Standing Rules
COMMITTEE_NAME_MAP = {
    # House committees - current as of 119th Congress
    "Oversight and Government Reform Committee": "Committee on Oversight and Accountability",
    "Oversight and Accountability Committee": "Committee on Oversight and Accountability",
    "Judiciary Committee": "Committee on the Judiciary",
    "Ways and Means Committee": "Committee on Ways and Means",
    "Energy and Commerce Committee": "Committee on Energy and Commerce",
    "Armed Services Committee": "Committee on Armed Services",
    "Financial Services Committee": "Committee on Financial Services",
    "Foreign Affairs Committee": "Committee on Foreign Affairs",
    "Education and Workforce Committee": "Committee on Education and the Workforce",
    "Education and Labor Committee": "Committee on Education and the Workforce",
    "Natural Resources Committee": "Committee on Natural Resources",
    "Transportation and Infrastructure Committee": "Committee on Transportation and Infrastructure",
    "Agriculture Committee": "Committee on Agriculture",
    "Appropriations Committee": "Committee on Appropriations",
    "Budget Committee": "Committee on the Budget",
    "Homeland Security Committee": "Committee on Homeland Security",
    "Rules Committee": "Committee on Rules",
    "Science, Space, and Technology Committee": "Committee on Science, Space, and Technology",
    "Small Business Committee": "Committee on Small Business",
    "Veterans' Affairs Committee": "Committee on Veterans' Affairs",
    "Committee on House Administration": "Committee on House Administration",
    # Senate committees
    "Finance Committee": "Committee on Finance",
    "Health, Education, Labor, and Pensions Committee": "Committee on Health, Education, Labor, and Pensions",
    "Homeland Security and Governmental Affairs Committee": "Committee on Homeland Security and Governmental Affairs",
    "Commerce, Science, and Transportation Committee": "Committee on Commerce, Science, and Transportation",
    "Banking, Housing, and Urban Affairs Committee": "Committee on Banking, Housing, and Urban Affairs",
    "Agriculture, Nutrition, and Forestry Committee": "Committee on Agriculture, Nutrition, and Forestry",
    "Energy and Natural Resources Committee": "Committee on Energy and Natural Resources",
    "Environment and Public Works Committee": "Committee on Environment and Public Works",
    "Foreign Relations Committee": "Committee on Foreign Relations",
    "Indian Affairs Committee": "Committee on Indian Affairs",
    "Intelligence Committee": "Select Committee on Intelligence",
    "Small Business and Entrepreneurship Committee": "Committee on Small Business and Entrepreneurship",
}


def normalize_committee_name(name):
    """Normalize to official committee name format."""
    if name in COMMITTEE_NAME_MAP:
        return COMMITTEE_NAME_MAP[name]
    # If already in "Committee on" format, keep it
    if name.startswith("Committee on"):
        return name
    return name


STOP_WORDS = {
    "a", "an", "the", "of", "to", "and", "in", "for", "on", "at", "by",
    "or", "is", "be", "as", "it", "with", "from", "that", "this", "are",
    "was", "were", "been", "have", "has", "had", "do", "does", "did",
    "act", "bill", "no", "not", "its", "our", "their", "all", "each",
    "which", "who", "whom", "what", "when", "where", "how", "than",
    "other", "into", "over", "such", "more", "some", "any",
    "united", "states", "america", "american", "congress", "federal",
    "national", "public", "law", "section", "title", "part",
    "amend", "provide", "require", "establish", "authorize", "direct",
    "make", "certain", "purposes", "related", "respect", "regarding",
}


def extract_significant_words(title):
    """Extract meaningful words from a bill title."""
    title = re.sub(r"\b(To |A bill to )", "", title, flags=re.IGNORECASE)
    words = re.findall(r"[a-z]+", title.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def get_committee_key(committee):
    """Create a unique key for a committee that preserves chamber distinction."""
    name = normalize_committee_name(committee.get("name", ""))
    chamber = committee.get("chamber", "")
    return f"{chamber}|{name}"


def build_model(training_data):
    """Build prediction model from training data."""

    # Separate mappings by chamber
    policy_committee = defaultdict(lambda: Counter())
    subject_committee = defaultdict(lambda: Counter())
    word_committee = defaultdict(lambda: Counter())
    committee_info = {}
    committee_freq = Counter()

    congresses_seen = set()

    for bill in training_data:
        committees = bill.get("committees", [])
        if not committees:
            continue

        congresses_seen.add(bill.get("congress", 0))
        bill_chamber = bill.get("originChamber", "")

        committee_keys = []
        for c in committees:
            name = c.get("name", "")
            chamber = c.get("chamber", "")
            if not name:
                continue

            key = get_committee_key(c)
            committee_keys.append(key)
            committee_freq[key] += 1

            if key not in committee_info:
                committee_info[key] = {
                    "name": normalize_committee_name(name),
                    "chamber": chamber,
                    "systemCode": c.get("systemCode", ""),
                }

        if not committee_keys:
            continue

        # policyArea mapping
        policy_area = bill.get("policyArea", "")
        if policy_area:
            for ckey in committee_keys:
                policy_committee[policy_area][ckey] += 1

        # Subject mapping
        for subj in bill.get("subjects", []):
            for ckey in committee_keys:
                subject_committee[subj][ckey] += 1

        # Title word mapping
        title = bill.get("title", "")
        words = extract_significant_words(title)
        for word in words:
            for ckey in committee_keys:
                word_committee[word][ckey] += 1

    # Build model
    model = {
        "policyArea": {},
        "subjects": {},
        "titleWords": {},
        "committees": committee_info,
        "stats": {
            "totalBills": len(training_data),
            "billsWithCommittees": sum(1 for b in training_data if b.get("committees")),
            "congresses": sorted(congresses_seen),
        },
    }

    # policyArea probabilities
    for pa, counts in policy_committee.items():
        total = sum(counts.values())
        if total < 3:
            continue
        probs = {key: count / total for key, count in counts.most_common(15)}
        model["policyArea"][pa] = {"total": total, "committees": probs}

    # Subject probabilities
    for subj, counts in subject_committee.items():
        total = sum(counts.values())
        if total < 3:
            continue
        probs = {key: count / total for key, count in counts.most_common(10)}
        model["subjects"][subj] = {"total": total, "committees": probs}

    # Title word probabilities
    for word, counts in word_committee.items():
        total = sum(counts.values())
        if total < 5:
            continue
        probs = {key: count / total for key, count in counts.most_common(8)}
        model["titleWords"][word] = {"total": total, "committees": probs}

    return model


def predict(model, title="", policy_area="", subjects=None, chamber="House"):
    """Predict committees for a bill."""
    scores = defaultdict(float)
    reasons = defaultdict(list)

    chamber_lower = chamber.lower()

    def add_score(comm_key, score, reason):
        scores[comm_key] += score
        reasons[comm_key].append(reason)

    # 1. Policy area (weight 3.0)
    if policy_area and policy_area in model["policyArea"]:
        pa_data = model["policyArea"][policy_area]
        for ckey, prob in pa_data["committees"].items():
            add_score(ckey, prob * 3.0, f"Policy area: {policy_area} ({prob:.0%})")

    # 2. Subjects (weight 1.5)
    if subjects:
        for subj in subjects:
            if subj in model["subjects"]:
                sd = model["subjects"][subj]
                for ckey, prob in sd["committees"].items():
                    add_score(ckey, prob * 1.5, f"Subject: {subj}")

    # 3. Title keywords (weight 0.5)
    if title:
        words = extract_significant_words(title)
        for word in words:
            if word in model["titleWords"]:
                wd = model["titleWords"][word]
                for ckey, prob in wd["committees"].items():
                    add_score(ckey, prob * 0.5, f"Keyword: \"{word}\"")

    # Filter by chamber
    filtered = {}
    for ckey, score in scores.items():
        info = model["committees"].get(ckey, {})
        comm_chamber = (info.get("chamber", "") or "").lower()
        if comm_chamber == chamber_lower or comm_chamber == "joint" or not comm_chamber:
            filtered[ckey] = score

    # Normalize
    total = sum(filtered.values()) or 1
    results = []
    for ckey, score in sorted(filtered.items(), key=lambda x: -x[1]):
        info = model["committees"].get(ckey, {})
        results.append({
            "key": ckey,
            "committee": info.get("name", ckey),
            "chamber": info.get("chamber", ""),
            "confidence": min(score / total, 1.0),
            "rawScore": score,
            "reasons": reasons.get(ckey, [])[:4],
        })

    return results[:10]


def evaluate_model(training_data, n_folds=5):
    """Cross-validation evaluation of the model."""
    random.seed(42)
    bills = [b for b in training_data if b.get("committees")]
    random.shuffle(bills)

    fold_size = len(bills) // n_folds
    results = {
        "top1": 0, "top3": 0, "top5": 0, "total": 0,
        "by_policy_area": defaultdict(lambda: {"top1": 0, "top3": 0, "total": 0}),
    }

    for fold in range(n_folds):
        test_start = fold * fold_size
        test_end = test_start + fold_size
        test_bills = bills[test_start:test_end]
        train_bills = bills[:test_start] + bills[test_end:]

        model = build_model(train_bills)

        for bill in test_bills:
            actual_keys = set()
            for c in bill.get("committees", []):
                actual_keys.add(get_committee_key(c))

            if not actual_keys:
                continue

            chamber = bill.get("originChamber", "House")
            preds = predict(model, bill.get("title", ""), bill.get("policyArea", ""),
                          bill.get("subjects", []), chamber)

            pred_keys = [p["key"] for p in preds]

            results["total"] += 1
            pa = bill.get("policyArea", "Unknown")

            # Check if any actual committee is in top-k predictions
            if any(k in actual_keys for k in pred_keys[:1]):
                results["top1"] += 1
                results["by_policy_area"][pa]["top1"] += 1
            if any(k in actual_keys for k in pred_keys[:3]):
                results["top3"] += 1
            if any(k in actual_keys for k in pred_keys[:5]):
                results["top5"] += 1
                results["by_policy_area"][pa]["top3"] += 1

            results["by_policy_area"][pa]["total"] += 1

    total = results["total"]
    eval_results = {
        "top1_accuracy": results["top1"] / total if total else 0,
        "top3_accuracy": results["top3"] / total if total else 0,
        "top5_accuracy": results["top5"] / total if total else 0,
        "total_evaluated": total,
        "folds": n_folds,
        "by_policy_area": {},
    }

    # Per-policy-area results
    for pa, counts in results["by_policy_area"].items():
        if counts["total"] >= 5:
            eval_results["by_policy_area"][pa] = {
                "top1": round(counts["top1"] / counts["total"], 3),
                "total": counts["total"],
            }

    return eval_results


def main():
    training_file = DATA_DIR / "training_data.json"
    if not training_file.exists():
        print("No training data found. Run collect_smart.py first.")
        return

    with open(training_file) as f:
        training_data = json.load(f)

    print(f"Loaded {len(training_data)} bills")
    bills_with_committees = sum(1 for b in training_data if b.get("committees"))
    print(f"Bills with committee data: {bills_with_committees}")

    # Count congresses
    congresses = Counter(b.get("congress", 0) for b in training_data)
    print(f"Congresses: {dict(congresses)}")

    # Evaluate first
    print("\n=== Cross-Validation Evaluation ===")
    eval_results = evaluate_model(training_data)
    print(f"Top-1 accuracy: {eval_results['top1_accuracy']:.1%}")
    print(f"Top-3 accuracy: {eval_results['top3_accuracy']:.1%}")
    print(f"Top-5 accuracy: {eval_results['top5_accuracy']:.1%}")
    print(f"Evaluated on: {eval_results['total_evaluated']} bills ({eval_results['folds']}-fold CV)")

    print("\nPer-policy-area top-1 accuracy:")
    for pa, data in sorted(eval_results["by_policy_area"].items(), key=lambda x: -x[1]["total"]):
        print(f"  {pa}: {data['top1']:.0%} ({data['total']} bills)")

    # Build final model on all data
    print("\n=== Building Final Model ===")
    model = build_model(training_data)
    model["stats"]["evaluation"] = eval_results

    # Save model
    model_file = OUTPUT_DIR / "model.json"
    with open(model_file, "w") as f:
        json.dump(model, f, indent=1)
    print(f"Model saved to {model_file}")
    print(f"  Policy areas: {len(model['policyArea'])}")
    print(f"  Subjects: {len(model['subjects'])}")
    print(f"  Title words: {len(model['titleWords'])}")
    print(f"  Committees: {len(model['committees'])}")

    # Test predictions
    print("\n=== Test Predictions ===")
    tests = [
        {"title": "To provide for improvements to the rivers and harbors of the United States",
         "policy_area": "Water Resources Development", "chamber": "House"},
        {"title": "To amend the Internal Revenue Code of 1986 to extend certain tax credits",
         "policy_area": "Taxation", "chamber": "House"},
        {"title": "To strengthen cybersecurity protections for critical infrastructure",
         "policy_area": "Science, Technology, Communications", "chamber": "House"},
        {"title": "To protect patients with pre-existing conditions",
         "policy_area": "Health", "chamber": "House"},
        {"title": "A bill to improve border security and immigration enforcement",
         "policy_area": "Immigration", "chamber": "Senate"},
    ]

    for test in tests:
        print(f"\n{test['chamber']} | {test['title'][:60]}...")
        print(f"Policy Area: {test['policy_area']}")
        results = predict(model, test["title"], test["policy_area"], chamber=test["chamber"])
        for r in results[:3]:
            print(f"  {r['confidence']:.0%} → {r['committee']} ({r['chamber']})")

    # Save dataset
    dataset_file = OUTPUT_DIR / "dataset.json"
    dataset = []
    for b in training_data:
        if b.get("committees"):
            dataset.append({
                "congress": b.get("congress"),
                "type": b.get("type"),
                "number": b.get("number"),
                "title": b.get("title"),
                "policyArea": b.get("policyArea", ""),
                "committees": [
                    {"name": normalize_committee_name(c.get("name", "")), "chamber": c.get("chamber", "")}
                    for c in b.get("committees", [])
                ],
                "subjects": b.get("subjects", [])[:5],
            })
    with open(dataset_file, "w") as f:
        json.dump(dataset, f, indent=1)
    print(f"\nDataset saved: {len(dataset)} bills to {dataset_file}")


if __name__ == "__main__":
    main()
