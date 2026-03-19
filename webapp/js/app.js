/**
 * Committee Predictor - Main application logic.
 * Uses the Congress.gov API for live bill lookups.
 */

// Congress.gov API key for live bill lookups (public demo key with standard rate limits)
const API_KEY = "DEMO_KEY";
let dataset = [];
let datasetPage = 0;
const PAGE_SIZE = 50;

// Initialize
document.addEventListener("DOMContentLoaded", async () => {
    const loaded = await CommitteeModel.load();
    if (!loaded) {
        document.getElementById("results-list").innerHTML =
            '<p>Failed to load prediction model. Please refresh.</p>';
        return;
    }

    // Populate policy area dropdowns
    const policyAreas = CommitteeModel.getPolicyAreas();
    const paSelect = document.getElementById("policy-area");
    const filterSelect = document.getElementById("dataset-filter");

    for (const pa of policyAreas) {
        paSelect.add(new Option(pa, pa));
        filterSelect.add(new Option(pa, pa));
    }

    // Load dataset
    try {
        const resp = await fetch("data/dataset.json");
        dataset = await resp.json();
        renderDataset();
        renderPatternChart();
    } catch (e) {
        console.error("Failed to load dataset:", e);
    }

    // Update stats with real evaluation data
    updateStatsDisplay();

    // Allow Enter key to trigger prediction
    document.getElementById("bill-title").addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            runPrediction();
        }
    });
});

/**
 * Update the accuracy section with real evaluation metrics.
 */
function updateStatsDisplay() {
    const stats = CommitteeModel.getStats();
    const eval_ = CommitteeModel.getEvaluation();

    function ordinal(n) {
        const s = ["th","st","nd","rd"], v = n % 100;
        return n + (s[(v-20)%10]||s[v]||s[0]);
    }

    let html = `Trained on <strong>${stats.billsWithCommittees || 0}</strong> bills `;
    if (stats.congresses && stats.congresses.length > 0) {
        const first = stats.congresses[0];
        const last = stats.congresses[stats.congresses.length - 1];
        html += `from the ${ordinal(first)} through ${ordinal(last)} Congresses. `;
    }
    html += `The model covers <strong>${CommitteeModel.getPolicyAreas().length}</strong> policy areas ` +
        `and <strong>${Object.keys(CommitteeModel.data.committees).length}</strong> committees.`;
    html += `<br><span style="font-size: 0.85rem; color: var(--text-light);">Model last updated: March 2026.</span>`;

    if (eval_) {
        html += `<br><br><strong>Cross-validated accuracy (${eval_.folds}-fold, ${eval_.total_evaluated} bills):</strong><br>`;
        html += `Top-1: <strong>${(eval_.top1_accuracy * 100).toFixed(1)}%</strong> · `;
        html += `Top-3: <strong>${(eval_.top3_accuracy * 100).toFixed(1)}%</strong> · `;
        html += `Top-5: <strong>${(eval_.top5_accuracy * 100).toFixed(1)}%</strong>`;

        // Show per-policy-area breakdown
        if (eval_.by_policy_area) {
            const areas = Object.entries(eval_.by_policy_area)
                .sort((a, b) => b[1].total - a[1].total)
                .slice(0, 10);

            if (areas.length > 0) {
                html += `<br><br><strong>Top-1 accuracy by policy area:</strong><br>`;
                html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2px 16px; margin-top: 4px; font-size: 0.85rem;">';
                for (const [pa, data] of areas) {
                    const pct = (data.top1 * 100).toFixed(0);
                    html += `<span>${pa}: <strong>${pct}%</strong> <span style="color: var(--text-light);">(n=${data.total})</span></span>`;
                }
                html += '</div>';
            }
        }
    }

    document.getElementById("accuracy-text").innerHTML = html;
}

/**
 * Run prediction from form inputs.
 */
function runPrediction() {
    const title = document.getElementById("bill-title").value.trim();
    const policyArea = document.getElementById("policy-area").value;
    const chamber = document.getElementById("chamber").value;
    const subjectsRaw = document.getElementById("subjects-input").value;
    const subjects = subjectsRaw ? subjectsRaw.split(",").map(s => s.trim()).filter(Boolean) : [];

    if (!title && !policyArea && subjects.length === 0) {
        document.getElementById("results").style.display = "block";
        document.getElementById("results-list").innerHTML =
            '<p style="color: var(--text-light);">Please enter a bill title, select a policy area, or provide subjects to get a prediction.</p>';
        return;
    }

    const predictions = CommitteeModel.predict(title, policyArea, subjects, chamber);
    displayPredictions(predictions, chamber);
}

/**
 * Display prediction results.
 */
function displayPredictions(predictions, chamber) {
    const container = document.getElementById("results");
    const list = document.getElementById("results-list");
    const explanation = document.getElementById("explanation");

    container.style.display = "block";

    if (predictions.length === 0) {
        list.innerHTML = '<p>No predictions available. Try providing more information about the bill.</p>';
        explanation.innerHTML = "";
        return;
    }

    let html = "";
    predictions.forEach((pred, i) => {
        const pct = Math.round(pred.confidence * 100);
        const barClass = pct >= 40 ? "confidence-high" : pct >= 20 ? "confidence-med" : "confidence-low";
        const reasonsHtml = pred.reasons.map(r => `<span>${escapeHtml(r)}</span>`).join(" · ");

        html += `
            <div class="result-card">
                <div class="result-rank">${i + 1}</div>
                <div class="result-bar-container">
                    <div class="result-name">${escapeHtml(pred.committee)}</div>
                    <div class="result-bar">
                        <div class="result-bar-fill ${barClass}" style="width: ${Math.max(pct, 2)}%"></div>
                    </div>
                    <div class="result-reasons">${reasonsHtml}</div>
                </div>
                <div class="result-confidence">${pct}%</div>
            </div>
        `;
    });

    list.innerHTML = html;

    // Multi-referral explanation
    const topPred = predictions[0];
    const multiReferral = predictions.filter(p => p.confidence > 0.15).length > 1;

    if (topPred.confidence > 0.5) {
        explanation.innerHTML = `<strong>High confidence:</strong> Based on historical referral patterns, this bill would most likely be referred to <strong>${escapeHtml(topPred.committee)}</strong>.`;
    } else if (multiReferral) {
        const topComms = predictions.filter(p => p.confidence > 0.15).map(p => `<strong>${escapeHtml(p.committee)}</strong>`);
        explanation.innerHTML = `<strong>Possible multiple referral:</strong> This bill touches jurisdictions of ${topComms.join(", ")}. In the House, the Speaker may order a joint, sequential, or split referral under Rule XII.`;
    } else {
        explanation.innerHTML = `<strong>Moderate confidence:</strong> The model favors <strong>${escapeHtml(topPred.committee)}</strong> but has limited signal. Providing a policy area will improve accuracy.`;
    }
}

/**
 * Look up a real bill from Congress.gov API and compare prediction vs. actual.
 */
async function lookupBill() {
    const congress = document.getElementById("lookup-congress").value;
    const type = document.getElementById("lookup-type").value;
    const number = document.getElementById("lookup-number").value;

    if (!number) return;

    const resultsDiv = document.getElementById("lookup-results");
    const billInfo = document.getElementById("lookup-bill-info");
    const actualDiv = document.getElementById("actual-committees");
    const predictedDiv = document.getElementById("predicted-committees");

    resultsDiv.style.display = "block";
    billInfo.innerHTML = '<p class="loading">Looking up bill</p>';
    actualDiv.innerHTML = "";
    predictedDiv.innerHTML = "";

    try {
        const baseUrl = `https://api.congress.gov/v3/bill/${congress}/${type}/${number}`;
        const detail = await apiGet(baseUrl);

        if (!detail || !detail.bill) {
            billInfo.innerHTML = "<p>Bill not found. Check the congress, type, and number.</p>";
            return;
        }

        const bill = detail.bill;
        const title = bill.title || "Untitled";
        const policyArea = bill.policyArea ? bill.policyArea.name : "";
        const chamber = bill.originChamber || "House";

        const typeLabels = {
            "hr": "H.R.", "s": "S.", "hjres": "H.J.Res.", "sjres": "S.J.Res.",
            "hconres": "H.Con.Res.", "sconres": "S.Con.Res.",
            "hres": "H.Res.", "sres": "S.Res."
        };
        const typeLabel = typeLabels[type] || type.toUpperCase();

        // Congress.gov URL
        const typeSlug = {
            "hr": "house-bill", "s": "senate-bill",
            "hjres": "house-joint-resolution", "sjres": "senate-joint-resolution",
            "hconres": "house-concurrent-resolution", "sconres": "senate-concurrent-resolution",
            "hres": "house-resolution", "sres": "senate-resolution",
        };
        const congressGovUrl = `https://www.congress.gov/bill/${congress}th-congress/${typeSlug[type] || "house-bill"}/${number}`;

        billInfo.innerHTML = `
            <h3><a href="${congressGovUrl}" target="_blank" style="color: inherit; text-decoration: underline;">${typeLabel} ${number}</a> — ${escapeHtml(title)}</h3>
            <div class="bill-meta">
                ${congress}th Congress · ${chamber} · Policy Area: ${policyArea || "Not assigned yet"}
            </div>
        `;

        // Fetch actual committees
        const commData = await apiGet(`${baseUrl}/committees`);
        const actualComms = [];
        if (commData && commData.committees) {
            for (const c of commData.committees) {
                actualComms.push({ name: c.name, chamber: c.chamber || "" });
            }
        }

        // Fetch subjects
        let subjects = [];
        const subjData = await apiGet(`${baseUrl}/subjects`);
        if (subjData && subjData.subjects && subjData.subjects.legislativeSubjects) {
            subjects = subjData.subjects.legislativeSubjects.map(s => s.name);
        }

        // Display actual committees
        if (actualComms.length > 0) {
            actualDiv.innerHTML = actualComms
                .map(c => `<span class="committee-tag actual">${escapeHtml(c.name)}<br><small>${c.chamber}</small></span>`)
                .join("");
        } else {
            actualDiv.innerHTML = "<p>No committee referral recorded yet.</p>";
        }

        // Run prediction
        const predictions = CommitteeModel.predict(title, policyArea, subjects, chamber);

        // Display predicted with match highlighting
        const actualNames = actualComms.map(c => c.name);
        predictedDiv.innerHTML = predictions.slice(0, 5)
            .map(p => {
                const isMatch = actualNames.includes(p.committee);
                const cls = isMatch ? "committee-tag match" : "committee-tag predicted";
                const pct = Math.round(p.confidence * 100);
                const checkmark = isMatch ? " &#10003;" : "";
                return `<span class="${cls}">${escapeHtml(p.committee)} (${pct}%)${checkmark}<br><small>${p.chamber}</small></span>`;
            })
            .join("");

        // Match accuracy indicator
        if (actualComms.length > 0) {
            const predNames = predictions.slice(0, 5).map(p => p.committee);
            const matches = actualNames.filter(n => predNames.includes(n));

            let indicator;
            if (matches.length === actualComms.length) {
                indicator = `<div class="match-indicator correct">All ${matches.length} committee(s) correctly predicted in top 5</div>`;
            } else if (matches.length > 0) {
                indicator = `<div class="match-indicator partial">${matches.length} of ${actualComms.length} committees matched in top 5</div>`;
            } else {
                // Check if primary committee is at least top-1
                const top1Match = actualNames.includes(predictions[0]?.committee);
                if (top1Match) {
                    indicator = `<div class="match-indicator correct">Primary committee correctly predicted</div>`;
                } else {
                    indicator = `<div class="match-indicator partial">Actual committee not in top-5 predictions</div>`;
                }
            }
            predictedDiv.innerHTML += indicator;
        }

        // Also show in the main prediction area
        displayPredictions(predictions, chamber);

    } catch (e) {
        billInfo.innerHTML = `<p>Error: ${escapeHtml(e.message)}. Check your connection and try again.</p>`;
    }
}

/**
 * Fetch from Congress.gov API.
 */
async function apiGet(url) {
    const sep = url.includes("?") ? "&" : "?";
    const fullUrl = `${url}${sep}api_key=${API_KEY}&format=json`;
    const resp = await fetch(fullUrl);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

/**
 * Render the pattern chart showing committee distribution by chamber.
 */
function renderPatternChart() {
    if (!CommitteeModel.loaded) return;

    const chartDiv = document.getElementById("pattern-chart");
    const houseCounts = {};
    const senateCounts = {};

    for (const bill of dataset) {
        for (const comm of bill.committees) {
            const name = typeof comm === "string" ? comm : comm.name;
            const chamber = typeof comm === "string" ? "" : (comm.chamber || "");
            if (chamber === "House" || (!chamber && bill.type === "HR")) {
                houseCounts[name] = (houseCounts[name] || 0) + 1;
            } else if (chamber === "Senate" || (!chamber && bill.type === "S")) {
                senateCounts[name] = (senateCounts[name] || 0) + 1;
            } else {
                houseCounts[name] = (houseCounts[name] || 0) + 1;
            }
        }
    }

    function renderBar(counts, label) {
        const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
        const max = sorted[0] ? sorted[0][1] : 1;
        let html = `<h4 style="font-size: 0.9rem; color: var(--primary); margin: 12px 0 8px;">${label}</h4>`;
        for (const [name, count] of sorted) {
            const width = Math.round((count / max) * 100);
            html += `
                <div class="chart-bar-group">
                    <div class="chart-label" title="${name}">${name}</div>
                    <div class="chart-bar" style="width: ${width}%">
                        <span>${count}</span>
                    </div>
                </div>
            `;
        }
        return html;
    }

    let html = '<h3 style="font-size: 1rem; color: var(--primary); margin-bottom: 4px;">Committee Referral Frequency</h3>';
    const stats = CommitteeModel.getStats();
    const congresses = (stats.congresses || []);
    const congStr = congresses.length > 0 ? `${congresses[0]}th\u2013${congresses[congresses.length-1]}th` : "";
    html += `<p style="color: var(--text-light); font-size: 0.85rem; margin-bottom: 8px;">From training data across ${congStr} Congresses</p>`;
    html += renderBar(houseCounts, "House Committees");
    html += renderBar(senateCounts, "Senate Committees");

    chartDiv.innerHTML = html;
}

/**
 * Render the dataset table.
 */
function renderDataset() {
    const filter = document.getElementById("dataset-filter").value;
    const filtered = filter
        ? dataset.filter(b => b.policyArea === filter)
        : dataset;

    const start = datasetPage * PAGE_SIZE;
    const page = filtered.slice(start, start + PAGE_SIZE);
    const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

    const tbody = document.getElementById("dataset-tbody");
    tbody.innerHTML = page.map(b => {
        const typeSlug = {
            "HR": "house-bill", "S": "senate-bill",
            "HJRES": "house-joint-resolution", "SJRES": "senate-joint-resolution",
        };
        const slug = typeSlug[b.type] || "house-bill";
        const url = `https://www.congress.gov/bill/${b.congress}th-congress/${slug}/${b.number}`;
        const comms = (b.committees || []).map(c => typeof c === "string" ? c : c.name).join(", ");

        return `
        <tr>
            <td><a href="${url}" target="_blank">${b.type} ${b.number}</a></td>
            <td>${escapeHtml((b.title || "").substring(0, 80))}${(b.title || "").length > 80 ? "..." : ""}</td>
            <td>${escapeHtml(b.policyArea || "—")}</td>
            <td>${escapeHtml(comms)}</td>
        </tr>`;
    }).join("");

    // Pagination
    const pagDiv = document.getElementById("pagination");
    if (totalPages <= 1) {
        pagDiv.innerHTML = `<span style="color: var(--text-light); font-size: 0.85rem;">${filtered.length} bills</span>`;
        return;
    }

    let pagHtml = "";
    if (datasetPage > 0) {
        pagHtml += `<button onclick="changePage(${datasetPage - 1})">Prev</button>`;
    }
    pagHtml += `<span style="padding: 6px 12px; font-size: 0.85rem; color: var(--text-light);">Page ${datasetPage + 1} of ${totalPages} (${filtered.length} bills)</span>`;
    if (datasetPage < totalPages - 1) {
        pagHtml += `<button onclick="changePage(${datasetPage + 1})">Next</button>`;
    }
    pagDiv.innerHTML = pagHtml;
}

function changePage(page) {
    datasetPage = page;
    renderDataset();
    document.getElementById("dataset-table-container").scrollTop = 0;
}

function filterDataset() {
    datasetPage = 0;
    renderDataset();
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
