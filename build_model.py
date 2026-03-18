#!/usr/bin/env python3
"""
Build a committee prediction model from training data.
Outputs a JSON model file that can be used client-side in the browser.

Model approach:
1. policyArea → committee probability distribution (strongest signal)
2. Legislative subject keywords → committee probability boosts
3. Title keyword → committee probability boosts
4. Chamber-specific committee filtering
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path("data")
OUTPUT_DIR = Path("webapp/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_committee_name(name):
    """Normalize committee names to handle variations."""
    # Remove "House " or "Senate " prefix for matching
    name = name.strip()
    # Standardize common variations
    replacements = {
        "House Committee on ": "",
        "Senate Committee on ": "",
        "Committee on ": "",
    }
    for old, new in replacements.items():
        if name.startswith(old):
            name = new + name[len(old):]
    return name.strip()


def build_model(training_data):
    """Build prediction model from training data."""

    # 1. policyArea → committee mapping
    policy_committee = defaultdict(lambda: Counter())
    # 2. Subject → committee mapping
    subject_committee = defaultdict(lambda: Counter())
    # 3. Title word → committee mapping
    word_committee = defaultdict(lambda: Counter())
    # 4. Committee metadata
    committee_info = {}
    # 5. Overall committee frequency
    committee_freq = Counter()

    for bill in training_data:
        committees = bill.get("committees", [])
        if not committees:
            continue

        committee_names = []
        for c in committees:
            name = c.get("name", "")
            if not name:
                continue
            committee_names.append(name)
            committee_freq[name] += 1

            # Store committee metadata
            if name not in committee_info:
                committee_info[name] = {
                    "name": name,
                    "chamber": c.get("chamber", ""),
                    "systemCode": c.get("systemCode", ""),
                }

        if not committee_names:
            continue

        # policyArea mapping
        policy_area = bill.get("policyArea", "")
        if policy_area:
            for cname in committee_names:
                policy_committee[policy_area][cname] += 1

        # Subject mapping
        for subj in bill.get("subjects", []):
            for cname in committee_names:
                subject_committee[subj][cname] += 1

        # Title word mapping (significant words only)
        title = bill.get("title", "")
        words = extract_significant_words(title)
        for word in words:
            for cname in committee_names:
                word_committee[word][cname] += 1

    # Convert to probability distributions
    model = {
        "policyArea": {},
        "subjects": {},
        "titleWords": {},
        "committees": {},
        "stats": {
            "totalBills": len(training_data),
            "billsWithCommittees": sum(1 for b in training_data if b.get("committees")),
        },
    }

    # policyArea probabilities
    for pa, counts in policy_committee.items():
        total = sum(counts.values())
        if total < 3:  # Skip rare policy areas
            continue
        probs = {name: count / total for name, count in counts.most_common(10)}
        model["policyArea"][pa] = {"total": total, "committees": probs}

    # Subject probabilities (only keep subjects with enough data)
    for subj, counts in subject_committee.items():
        total = sum(counts.values())
        if total < 5:
            continue
        probs = {name: count / total for name, count in counts.most_common(8)}
        model["subjects"][subj] = {"total": total, "committees": probs}

    # Title word probabilities (only common/distinctive words)
    for word, counts in word_committee.items():
        total = sum(counts.values())
        if total < 5:
            continue
        probs = {name: count / total for name, count in counts.most_common(5)}
        model["titleWords"][word] = {"total": total, "committees": probs}

    # Committee info
    model["committees"] = committee_info

    return model


STOP_WORDS = {
    "a", "an", "the", "of", "to", "and", "in", "for", "on", "at", "by",
    "or", "is", "be", "as", "it", "with", "from", "that", "this", "are",
    "was", "were", "been", "have", "has", "had", "do", "does", "did",
    "act", "bill", "no", "not", "its", "our", "their", "all", "each",
    "which", "who", "whom", "what", "when", "where", "how", "than",
    "other", "into", "over", "such", "more", "some", "any",
    "united", "states", "america", "american", "congress", "federal",
    "national", "public", "law", "section", "title", "part",
}


def extract_significant_words(title):
    """Extract meaningful words from a bill title."""
    # Remove common bill prefixes
    title = re.sub(r"\b(To |A bill to )", "", title, flags=re.IGNORECASE)
    words = re.findall(r"[a-z]+", title.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def predict_committees(model, title="", policy_area="", subjects=None, chamber="House"):
    """Predict committees for a bill given its features."""
    scores = defaultdict(float)
    explanations = defaultdict(list)

    # 1. Policy area (strongest signal, weight 3.0)
    if policy_area and policy_area in model["policyArea"]:
        pa_data = model["policyArea"][policy_area]
        for comm, prob in pa_data["committees"].items():
            scores[comm] += prob * 3.0
            explanations[comm].append(f"Policy area '{policy_area}' ({prob:.0%})")

    # 2. Subjects (weight 1.5 each, but capped)
    if subjects:
        for subj in subjects:
            if subj in model["subjects"]:
                subj_data = model["subjects"][subj]
                for comm, prob in subj_data["committees"].items():
                    scores[comm] += prob * 1.5
                    explanations[comm].append(f"Subject '{subj}'")

    # 3. Title words (weight 0.5 each)
    if title:
        words = extract_significant_words(title)
        for word in words:
            if word in model["titleWords"]:
                word_data = model["titleWords"][word]
                for comm, prob in word_data["committees"].items():
                    scores[comm] += prob * 0.5
                    explanations[comm].append(f"Keyword '{word}'")

    # Filter by chamber
    if chamber:
        chamber_match = chamber.lower()
        filtered = {}
        for comm, score in scores.items():
            comm_info = model["committees"].get(comm, {})
            comm_chamber = comm_info.get("chamber", "").lower()
            if comm_chamber == chamber_match or not comm_chamber:
                filtered[comm] = score
        scores = filtered

    # Normalize scores to probabilities
    total = sum(scores.values()) if scores else 1
    results = []
    for comm, score in sorted(scores.items(), key=lambda x: -x[1]):
        results.append({
            "committee": comm,
            "confidence": min(score / total, 1.0) if total > 0 else 0,
            "rawScore": score,
            "reasons": explanations.get(comm, [])[:3],
        })

    return results[:10]


def main():
    # Load training data
    training_file = DATA_DIR / "training_data.json"
    if not training_file.exists():
        print("No training data found. Run collect_smart.py first.")
        return

    with open(training_file) as f:
        training_data = json.load(f)

    print(f"Loaded {len(training_data)} bills")
    bills_with_committees = sum(1 for b in training_data if b.get("committees"))
    print(f"Bills with committee data: {bills_with_committees}")

    # Build the model
    model = build_model(training_data)

    # Save model for web app
    model_file = OUTPUT_DIR / "model.json"
    with open(model_file, "w") as f:
        json.dump(model, f, indent=1)
    print(f"Model saved to {model_file}")
    print(f"  Policy areas: {len(model['policyArea'])}")
    print(f"  Subjects: {len(model['subjects'])}")
    print(f"  Title words: {len(model['titleWords'])}")
    print(f"  Committees: {len(model['committees'])}")

    # Test predictions
    print("\n--- Test Predictions ---")
    tests = [
        {"title": "To provide for improvements to the rivers and harbors of the United States",
         "policy_area": "Water Resources Development", "chamber": "House"},
        {"title": "To amend the Internal Revenue Code of 1986 to extend certain tax credits",
         "policy_area": "Taxation", "chamber": "House"},
        {"title": "To strengthen the national defense through cybersecurity improvements",
         "policy_area": "Armed Forces and National Security", "chamber": "House"},
        {"title": "To protect patients with pre-existing conditions",
         "policy_area": "Health", "chamber": "House"},
    ]

    for test in tests:
        print(f"\nTitle: {test['title'][:60]}...")
        print(f"Policy Area: {test['policy_area']}")
        results = predict_committees(model, test["title"], test["policy_area"], chamber=test["chamber"])
        for r in results[:3]:
            print(f"  {r['confidence']:.0%} → {r['committee']}")
            for reason in r["reasons"]:
                print(f"       {reason}")

    # Also save the full training dataset as a browsable dataset
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
                "committees": [c.get("name") for c in b.get("committees", [])],
                "subjects": b.get("subjects", [])[:5],
            })
    with open(dataset_file, "w") as f:
        json.dump(dataset, f, indent=1)
    print(f"\nDataset saved: {len(dataset)} bills to {dataset_file}")


if __name__ == "__main__":
    main()
