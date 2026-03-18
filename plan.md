# Bills to Committee - Implementation Plan

## Goal
Predict which congressional committees a bill will be referred to, based on its title, subjects, and sponsor info. Deliver as a polished web app hosted on GitHub Pages.

## Approach

### Data Pipeline
1. Use congress.gov API to collect bill data from recent congresses (116-118)
2. For each bill, collect: title, policyArea, legislativeSubjects, sponsor info, bill type, committee referrals
3. Store as structured JSON dataset

### Prediction Model
- **Primary signal**: policyArea → committee mapping (strong correlation with jurisdiction)
- **Secondary signals**: legislative subjects, title keywords, bill type, sponsor party
- Build a lightweight classifier that runs entirely in the browser (no server needed)
- Use a trained lookup/scoring model exported as JSON weights

### Web App (GitHub Pages)
- **Prediction tool**: Paste a bill title or enter subjects → get predicted committee(s) with confidence scores
- **Browser integration**: Bookmarklet or userscript that adds predictions to congress.gov bill pages
- **Dataset explorer**: Browse the historical referral patterns

### Tech Stack
- Python for data collection and model training
- Static HTML/CSS/JS for the web app (no build step needed)
- GitHub Pages for hosting

## Phases
1. **Data Collection** - Gather bills + committee referrals from API
2. **Analysis & Model** - Build prediction model from historical patterns
3. **Web App** - Interactive prediction interface
4. **Polish** - DC agent review and iteration
5. **After Action Report**
