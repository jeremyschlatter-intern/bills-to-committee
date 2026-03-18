# After Action Report: Committee Predictor

## Project Summary

**Goal:** Build a tool that predicts which congressional committees a bill will be referred to, using historical referral patterns. Make it available as a dataset or web app.

**Result:** A working web application at [jeremyschlatter-intern.github.io/bills-to-committee](https://jeremyschlatter-intern.github.io/bills-to-committee/) that predicts committee referrals with **78.7% top-1 accuracy** and **94.2% top-3 accuracy**, trained on 2,062 bills from the 116th-118th Congresses. Features include a prediction tool, live bill lookup via the Congress.gov API, and a historical dataset explorer.

---

## Process

### Phase 1: Research & Data Collection

**What I did:** Investigated the Congress.gov API to understand what data was available for building a prediction model. I discovered the API provides bill titles, CRS policy areas, legislative subject tags, committee referral records, and sponsor information -- all the signals needed for committee prediction.

**Obstacle: Python's default User-Agent blocked by Congress.gov API.** My initial data collection scripts failed with HTTP 403 errors, even though the same URLs worked with `curl`. After debugging, I identified that Congress.gov blocks Python's default `urllib` User-Agent string. Fixed by adding a custom `User-Agent` header.

**Obstacle: API rate limiting and data volume.** Collecting detailed data for each bill requires 3 API calls (bill detail, committees, subjects). At ~0.1 seconds per call, collecting thousands of bills takes hours. I designed a two-phase collection strategy:
- Phase 1: Bulk-collect 20,000 bill listings (250 per API call, only 80 calls total)
- Phase 2: Selectively enrich a representative sample with full details

This hybrid approach was much more efficient than naively fetching every bill's details.

**Obstacle: Data directory lost during git branch switching.** When deploying to GitHub Pages via a `gh-pages` branch, `git checkout` removed untracked files in the data directory. One large data collection run (~3,000 bills, ~9,000 API calls) was lost because the save operation ran after the directory was gone. I implemented recovery by re-running collection and added JSON corruption recovery code for a partially-written file.

### Phase 2: Model Design & Evaluation

**Approach:** I chose a probability-based model that combines three signals:

1. **CRS Policy Area** (strongest signal, weight 3.0): Congressional committees have defined jurisdictions that align closely with CRS policy areas. A bill tagged "Taxation" will almost always go to Ways & Means (House) or Finance (Senate).

2. **Legislative Subject Tags** (medium signal, weight 1.5): Finer-grained CRS subject tags provide additional discrimination within a policy area.

3. **Title Keywords** (weak signal, weight 0.5): Keywords in the bill title provide a fallback when policy area and subjects are unavailable.

The model runs entirely in the browser -- no server required. This was a deliberate design choice: it makes the tool deployable as a static site on GitHub Pages with zero infrastructure cost.

**Key design decision: Chamber separation.** House and Senate committees are distinct bodies with different names and somewhat different jurisdictions. My initial model conflated them (e.g., treating "Judiciary Committee" as one entity). After feedback from the DC review agent, I separated them using a `Chamber|Name` keying system. This improved both accuracy and usability.

**Evaluation:** I implemented 5-fold cross-validation to provide honest accuracy metrics. Results:
- **Top-1 accuracy: 78.7%** (correct primary committee)
- **Top-3 accuracy: 94.2%** (correct committee in top 3 predictions)
- **Top-5 accuracy: 96.8%** (correct committee in top 5 predictions)

Accuracy varies significantly by policy area. Taxation (98%), Education (96%), and Crime (90%) are highly predictable because those jurisdictions are clear-cut. Commerce (60%), Environmental Protection (56%), and Science/Technology (57%) are harder because bills in those areas often span multiple committee jurisdictions.

### Phase 3: Web Application

**Built a static web app** with three main features:

1. **Prediction Tool:** Enter a bill title, optionally select a policy area and chamber, and get ranked committee predictions with confidence scores and explanations.

2. **Live Bill Lookup:** Enter a real bill number (e.g., H.R. 1, 118th Congress) and the app fetches the actual committee referral from Congress.gov, runs a prediction, and shows a side-by-side comparison highlighting matches.

3. **Historical Dataset Explorer:** Browse 2,062 training bills with policy areas, committees, and links to Congress.gov. Filterable by policy area. Includes a frequency chart of committee referrals split by chamber.

### Phase 4: DC Expert Review & Iteration

I created an agent playing the role of the DC policy expert who proposed this project (Daniel Schuman). This agent provided three rounds of increasingly specific feedback:

**Round 1 (harsh):** Called it "closer to a toy demo than a tool I'd hand to a Hill staffer." Key criticisms: insufficient training data (only 700 bills from one Congress), House/Senate committees conflated, informal committee names, vague accuracy claims, exposed API key.

**Round 2 (improved):** Acknowledged "substantial improvement." Remaining issues: committee names still not official, API key still exposed, inaccurate text claiming data from "Congresses 114-118" when actual coverage was 116-118, no version stamp.

**Round 3 (approved):** Grade of **A-**. All five must-fix items addressed. Said "Ship it" and would share with Hill colleagues as a proof of concept.

---

## Key Obstacles & Resolutions

| Obstacle | Resolution |
|----------|-----------|
| Congress.gov API blocks Python requests | Added custom User-Agent header |
| Slow API data collection (3 calls per bill) | Two-phase strategy: bulk list + selective enrichment |
| Lost data directory during git operations | Recovery code + re-collection |
| Corrupted JSON from overlapping file writes | JSON recovery parser that truncates at last valid object |
| House/Senate committee conflation | `Chamber\|Name` key format separating all committees |
| Informal committee names | Name normalization map to official "Committee on X" format |
| Outdated committee name ("Oversight and Government Reform") | Mapped to current "Oversight and Accountability" |
| Vague accuracy claims | Rigorous 5-fold cross-validation with per-policy-area breakdown |
| Static site can't proxy API calls | Accepted tradeoff: client-side API calls with demo key, noted in code |

---

## What I Would Do Differently

1. **Start with more data.** The first prototype had only 700 bills. Starting with the two-phase collection strategy from the beginning would have saved significant iteration time.

2. **Official committee names from the start.** The Congress.gov API returns informal names (e.g., "Judiciary Committee"). I should have built the normalization layer immediately rather than after review feedback.

3. **Avoid git branch switching with untracked data files.** The data loss from `git checkout` was avoidable. I should have committed the data files to a data branch or used a separate directory outside the repo.

---

## Technical Summary

- **Data:** 2,062 bills with full committee/subject/policy area data from 116th-118th Congresses, collected via Congress.gov API (~9,000 API calls)
- **Model:** Weighted probability model combining policy area, legislative subjects, and title keywords. Runs client-side in the browser.
- **Accuracy:** 78.7% top-1 / 94.2% top-3 / 96.8% top-5 (5-fold cross-validated)
- **Deployment:** Static site on GitHub Pages, zero infrastructure
- **Live at:** https://jeremyschlatter-intern.github.io/bills-to-committee/
- **Source:** https://github.com/jeremyschlatter-intern/bills-to-committee

---

## Tools & Technologies

- Python 3: Data collection, model training, evaluation
- JavaScript: Browser-side prediction engine and UI
- Congress.gov API: Bill data, committee referrals, legislative subjects
- GitHub Pages: Hosting (free, no server needed)

The entire project was built autonomously by Claude Code, including data collection, model design, web development, deployment, and iterative refinement based on simulated expert feedback.
