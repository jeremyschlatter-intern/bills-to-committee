/**
 * Committee Prediction Model - Browser-side inference engine.
 * Loads the trained model JSON and provides prediction functions.
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

        const addScore = (comm, score, reason) => {
            scores[comm] = (scores[comm] || 0) + score;
            if (!reasons[comm]) reasons[comm] = [];
            reasons[comm].push(reason);
        };

        // 1. Policy area signal (weight 3.0)
        if (policyArea && this.data.policyArea[policyArea]) {
            const pa = this.data.policyArea[policyArea];
            for (const [comm, prob] of Object.entries(pa.committees)) {
                addScore(comm, prob * 3.0, `Policy area: ${policyArea} (${Math.round(prob * 100)}%)`);
            }
        }

        // 2. Auto-detect policy area from title if not provided
        if (!policyArea && title) {
            const detected = this.detectPolicyArea(title);
            if (detected) {
                const pa = this.data.policyArea[detected];
                for (const [comm, prob] of Object.entries(pa.committees)) {
                    addScore(comm, prob * 2.0, `Detected policy: ${detected} (${Math.round(prob * 100)}%)`);
                }
            }
        }

        // 3. Subject signals (weight 1.5)
        for (const subj of subjects) {
            const trimmed = subj.trim();
            if (trimmed && this.data.subjects[trimmed]) {
                const sd = this.data.subjects[trimmed];
                for (const [comm, prob] of Object.entries(sd.committees)) {
                    addScore(comm, prob * 1.5, `Subject: ${trimmed}`);
                }
            }
        }

        // 4. Title keyword signals (weight 0.5)
        if (title) {
            const words = this.extractWords(title);
            for (const word of words) {
                if (this.data.titleWords[word]) {
                    const wd = this.data.titleWords[word];
                    for (const [comm, prob] of Object.entries(wd.committees)) {
                        addScore(comm, prob * 0.5, `Keyword: "${word}"`);
                    }
                }
            }
        }

        // Filter by chamber
        const chamberLower = chamber.toLowerCase();
        const filtered = {};
        for (const [comm, score] of Object.entries(scores)) {
            const info = this.data.committees[comm];
            if (!info) continue;
            const commChamber = (info.chamber || "").toLowerCase();
            if (commChamber === chamberLower || commChamber === "" || commChamber === "joint") {
                filtered[comm] = score;
            }
        }

        // Normalize and sort
        const total = Object.values(filtered).reduce((a, b) => a + b, 0) || 1;
        const results = Object.entries(filtered)
            .map(([comm, score]) => ({
                committee: comm,
                confidence: Math.min(score / total, 1.0),
                rawScore: score,
                reasons: (reasons[comm] || []).slice(0, 4),
                chamber: (this.data.committees[comm] || {}).chamber || "",
            }))
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
            "Health": ["health", "medical", "medicare", "medicaid", "hospital", "drug", "patient", "disease", "pharmaceutical"],
            "Taxation": ["tax", "revenue", "internal revenue", "irs", "deduction", "refund"],
            "Armed Forces and National Security": ["defense", "military", "armed forces", "veterans", "national security", "army", "navy"],
            "Crime and Law Enforcement": ["crime", "criminal", "law enforcement", "police", "prison", "sentencing", "felony"],
            "Education": ["education", "school", "student", "teacher", "college", "university", "elementary", "secondary"],
            "Energy": ["energy", "electricity", "renewable", "solar", "wind", "oil", "gas", "nuclear", "fossil fuel"],
            "Immigration": ["immigration", "immigrant", "visa", "citizenship", "naturalization", "border", "deportation"],
            "Environmental Protection": ["environment", "pollution", "emissions", "climate", "epa", "clean air", "clean water"],
            "Finance and Financial Sector": ["bank", "financial", "securities", "wall street", "lending", "credit", "mortgage"],
            "Transportation and Public Works": ["transportation", "highway", "railroad", "aviation", "transit", "bridge", "road"],
            "Agriculture and Food": ["agriculture", "farm", "food", "crop", "livestock", "usda", "nutrition"],
            "Government Operations and Politics": ["government", "federal employees", "civil service", "oversight", "procurement", "gsa"],
            "International Affairs": ["foreign", "international", "diplomacy", "ambassador", "treaty", "sanctions", "trade"],
            "Labor and Employment": ["labor", "worker", "employment", "wage", "union", "workplace", "osha", "retirement"],
            "Science, Technology, Communications": ["technology", "science", "cyber", "internet", "broadband", "telecom", "space", "nasa"],
            "Commerce": ["commerce", "trade", "business", "consumer", "ftc", "small business", "patent"],
            "Public Lands and Natural Resources": ["public lands", "national park", "wildlife", "forest", "mining", "water resources"],
            "Housing and Community Development": ["housing", "hud", "rent", "mortgage", "homeless", "community development"],
            "Social Welfare": ["social security", "welfare", "poverty", "child care", "disability", "snap", "food stamps"],
            "Water Resources Development": ["water resources", "dam", "flood", "irrigation", "harbor", "waterway", "corps of engineers"],
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
        return Object.values(this.data.committees).sort((a, b) => a.name.localeCompare(b.name));
    },

    getStats() {
        if (!this.loaded) return {};
        return this.data.stats || {};
    }
};
