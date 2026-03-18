/**
 * Committee Prediction Model - Browser-side inference engine.
 * Loads the trained model JSON and provides prediction functions.
 *
 * Committee keys are "Chamber|Name" format to keep House and Senate
 * committees separate (e.g., "House|Judiciary Committee").
 */

const CommitteeModel = {
    data: null,
    loaded: false,

    STOP_WORDS: new Set([
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
    ]),

    async load() {
        try {
            const resp = await fetch("data/model.json");
            this.data = await resp.json();
            this.loaded = true;
            return true;
        } catch (e) {
            console.error("Failed to load model:", e);
            return false;
        }
    },

    extractWords(title) {
        const words = title.toLowerCase().match(/[a-z]+/g) || [];
        return words.filter(w => !this.STOP_WORDS.has(w) && w.length > 2);
    },

    /**
     * Parse a committee key like "House|Judiciary Committee"
     */
    parseKey(key) {
        const idx = key.indexOf("|");
        if (idx === -1) return { chamber: "", name: key };
        return { chamber: key.substring(0, idx), name: key.substring(idx + 1) };
    },

    /**
     * Predict committees for a bill.
     * @param {string} title - Bill title or description
     * @param {string} policyArea - Policy area (optional)
     * @param {string[]} subjects - Legislative subjects (optional)
     * @param {string} chamber - "House" or "Senate"
     * @returns {Array} Sorted predictions with confidence and reasons
     */
    predict(title = "", policyArea = "", subjects = [], chamber = "House") {
        if (!this.loaded) return [];

        const scores = {};
        const reasons = {};

        const addScore = (key, score, reason) => {
            scores[key] = (scores[key] || 0) + score;
            if (!reasons[key]) reasons[key] = [];
            reasons[key].push(reason);
        };

        // 1. Policy area signal (weight 3.0)
        if (policyArea && this.data.policyArea[policyArea]) {
            const pa = this.data.policyArea[policyArea];
            for (const [key, prob] of Object.entries(pa.committees)) {
                addScore(key, prob * 3.0, `Policy area: ${policyArea} (${Math.round(prob * 100)}%)`);
            }
        }

        // 2. Auto-detect policy area from title if not provided
        if (!policyArea && title) {
            const detected = this.detectPolicyArea(title);
            if (detected) {
                const pa = this.data.policyArea[detected];
                if (pa) {
                    for (const [key, prob] of Object.entries(pa.committees)) {
                        addScore(key, prob * 2.0, `Detected policy: ${detected} (${Math.round(prob * 100)}%)`);
                    }
                }
            }
        }

        // 3. Subject signals (weight 1.5)
        for (const subj of subjects) {
            const trimmed = subj.trim();
            if (trimmed && this.data.subjects[trimmed]) {
                const sd = this.data.subjects[trimmed];
                for (const [key, prob] of Object.entries(sd.committees)) {
                    addScore(key, prob * 1.5, `Subject: ${trimmed}`);
                }
            }
        }

        // 4. Title keyword signals (weight 0.5)
        if (title) {
            const words = this.extractWords(title);
            for (const word of words) {
                if (this.data.titleWords[word]) {
                    const wd = this.data.titleWords[word];
                    for (const [key, prob] of Object.entries(wd.committees)) {
                        addScore(key, prob * 0.5, `Keyword: "${word}"`);
                    }
                }
            }
        }

        // Filter by chamber
        const chamberLower = chamber.toLowerCase();
        const filtered = {};
        for (const [key, score] of Object.entries(scores)) {
            const info = this.data.committees[key];
            if (!info) continue;
            const commChamber = (info.chamber || "").toLowerCase();
            if (commChamber === chamberLower || commChamber === "joint" || commChamber === "") {
                filtered[key] = score;
            }
        }

        // Normalize and sort
        const total = Object.values(filtered).reduce((a, b) => a + b, 0) || 1;
        const results = Object.entries(filtered)
            .map(([key, score]) => {
                const info = this.data.committees[key] || {};
                return {
                    key,
                    committee: info.name || key,
                    chamber: info.chamber || "",
                    confidence: Math.min(score / total, 1.0),
                    rawScore: score,
                    reasons: (reasons[key] || []).slice(0, 4),
                };
            })
            .sort((a, b) => b.confidence - a.confidence)
            .slice(0, 8);

        return results;
    },

    /**
     * Try to detect policy area from title text.
     */
    detectPolicyArea(title) {
        const lower = title.toLowerCase();
        const keywords = {
            "Health": ["health", "medical", "medicare", "medicaid", "hospital", "drug", "patient", "disease", "pharmaceutical", "nursing"],
            "Taxation": ["tax", "revenue", "internal revenue", "irs", "deduction", "refund", "income tax"],
            "Armed Forces and National Security": ["defense", "military", "armed forces", "national security", "army", "navy", "pentagon", "dod"],
            "Crime and Law Enforcement": ["crime", "criminal", "law enforcement", "police", "prison", "sentencing", "felony", "trafficking"],
            "Education": ["education", "school", "student", "teacher", "college", "university", "elementary", "higher education"],
            "Energy": ["energy", "electricity", "renewable", "solar", "wind", "oil", "gas", "nuclear", "fossil fuel", "pipeline"],
            "Immigration": ["immigration", "immigrant", "visa", "citizenship", "naturalization", "border", "deportation", "asylum"],
            "Environmental Protection": ["environment", "pollution", "emissions", "climate", "epa", "clean air", "clean water", "endangered"],
            "Finance and Financial Sector": ["bank", "financial", "securities", "wall street", "lending", "credit", "mortgage", "fdic"],
            "Transportation and Public Works": ["transportation", "highway", "railroad", "aviation", "transit", "bridge", "road", "faa"],
            "Agriculture and Food": ["agriculture", "farm", "food", "crop", "livestock", "usda", "nutrition", "snap"],
            "Government Operations and Politics": ["government", "federal employees", "civil service", "oversight", "procurement", "gsa", "foia"],
            "International Affairs": ["foreign", "international", "diplomacy", "ambassador", "treaty", "sanctions", "foreign aid"],
            "Labor and Employment": ["labor", "worker", "employment", "wage", "union", "workplace", "osha", "retirement", "pension"],
            "Science, Technology, Communications": ["technology", "science", "cyber", "internet", "broadband", "telecom", "space", "nasa", "ai", "artificial intelligence"],
            "Commerce": ["commerce", "trade", "business", "consumer", "ftc", "small business", "patent", "intellectual property"],
            "Public Lands and Natural Resources": ["public lands", "national park", "wildlife", "forest", "mining", "water resources", "wilderness"],
            "Housing and Community Development": ["housing", "hud", "rent", "mortgage", "homeless", "community development", "affordable housing"],
            "Social Welfare": ["social security", "welfare", "poverty", "child care", "disability", "supplemental", "food stamps"],
            "Water Resources Development": ["water resources", "dam", "flood", "irrigation", "harbor", "waterway", "corps of engineers", "levee"],
            "Veterans' Affairs": ["veteran", "va ", "gi bill", "veterans affairs", "military service", "service member"],
            "Native Americans": ["tribal", "native american", "indian", "indigenous", "reservation"],
            "Emergency Management": ["emergency", "fema", "disaster", "hurricane", "wildfire", "earthquake"],
        };

        let bestMatch = "";
        let bestScore = 0;

        for (const [area, words] of Object.entries(keywords)) {
            let score = 0;
            for (const word of words) {
                if (lower.includes(word)) score += word.split(" ").length;
            }
            if (score > bestScore) {
                bestScore = score;
                bestMatch = area;
            }
        }

        return bestScore >= 1 ? bestMatch : "";
    },

    getPolicyAreas() {
        if (!this.loaded) return [];
        return Object.keys(this.data.policyArea).sort();
    },

    getCommitteeList() {
        if (!this.loaded) return [];
        return Object.entries(this.data.committees)
            .map(([key, info]) => ({ key, ...info }))
            .sort((a, b) => a.name.localeCompare(b.name));
    },

    getStats() {
        if (!this.loaded) return {};
        return this.data.stats || {};
    },

    getEvaluation() {
        if (!this.loaded || !this.data.stats) return null;
        return this.data.stats.evaluation || null;
    }
};
