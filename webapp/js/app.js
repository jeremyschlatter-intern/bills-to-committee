/**
 * Committee Predictor - Main application logic.
 */

const API_KEY = "CONGRESS_API_KEY";
let dataset = [];
let datasetPage = 0;
const PAGE_SIZE = 50;

// Initialize
document.addEventListener("DOMContentLoaded", async () => {
    // Load model
    const loaded = await CommitteeModel.load();
    if (!loaded) {
        document.getElementById("results-list").innerHTML =
            '<p class="loading">Failed to load prediction model.</p>';
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

    // Update stats
    const stats = CommitteeModel.getStats();
    document.getElementById("accuracy-text").innerHTML =
        `Trained on <strong>${stats.billsWithCommittees || 0}</strong> bills ` +
        `from Congresses 114-118 (2015-2024) with known committee referrals. ` +
        `The model covers <strong>${policyAreas.length}</strong> policy areas and ` +
        `<strong>${Object.keys(CommitteeModel.data.committees).length}</strong> committees. ` +
        `Policy area is the strongest predictor — when provided, top-1 accuracy typically exceeds 70%.`;
});

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
        alert("Please enter a bill title, select a policy area, or provide subjects.");
        return;
    }

    const predictions = CommitteeModel.predict(title, policyArea, subjects, chamber);
    displayPredictions(predictions);
}

/**
 * Display prediction results.
 */
function displayPredictions(predictions) {
    const container = document.getElementById("results");
    const list = document.getElementById("results-list");
    const explanation = document.getElementById("explanation");

    container.style.display = "block";

    if (predictions.length === 0) {
        list.innerHTML = '<p>No predictions available. Try providing more information.</p>';
        explanation.innerHTML = "";
        return;
    }

    let html = "";
    predictions.forEach((pred, i) => {
        const pct = Math.round(pred.confidence * 100);
        const barClass = pct >= 40 ? "confidence-high" : pct >= 20 ? "confidence-med" : "confidence-low";
        const reasonsHtml = pred.reasons.map(r => `<span>${r}</span>`).join(" · ");

        html += `
            <div class="result-card">
                <div class="result-rank">${i + 1}</div>
                <div class="result-bar-container">
                    <div class="result-name">${pred.committee}</div>
                    <div class="result-bar">
                        <div class="result-bar-fill ${barClass}" style="width: ${pct}%"></div>
                    </div>
                    <div class="result-reasons">${reasonsHtml}</div>
                </div>
                <div class="result-confidence">${pct}%</div>
            </div>
        `;
    });

    list.innerHTML = html;

    // Explanation
    const topPred = predictions[0];
    if (topPred.confidence > 0.5) {
        explanation.innerHTML = `<strong>High confidence:</strong> The model strongly predicts referral to <strong>${topPred.committee}</strong>. ${topPred.reasons[0] || ""}`;
    } else if (topPred.confidence > 0.3) {
        explanation.innerHTML = `<strong>Moderate confidence:</strong> The model favors <strong>${topPred.committee}</strong>, but this bill may touch multiple committee jurisdictions.`;
    } else {
        explanation.innerHTML = `<strong>Multiple jurisdictions:</strong> This bill spans several policy areas and may be referred to multiple committees or have a split referral.`;
    }

    // Animate bars
    setTimeout(() => {
        document.querySelectorAll(".result-bar-fill").forEach(bar => {
            bar.style.width = bar.style.width; // trigger reflow
        });
    }, 50);
}

/**
 * Look up a real bill from Congress.gov API.
 */
async function lookupBill() {
    const congress = document.getElementById("lookup-congress").value;
    const type = document.getElementById("lookup-type").value;
    const number = document.getElementById("lookup-number").value;

    if (!number) {
        alert("Please enter a bill number.");
        return;
    }

    const resultsDiv = document.getElementById("lookup-results");
    const billInfo = document.getElementById("lookup-bill-info");
    const actualDiv = document.getElementById("actual-committees");
    const predictedDiv = document.getElementById("predicted-committees");

    resultsDiv.style.display = "block";
    billInfo.innerHTML = '<p class="loading">Looking up bill</p>';
    actualDiv.innerHTML = "";
    predictedDiv.innerHTML = "";

    try {
        // Fetch bill detail
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
        const typeLabel = type.toUpperCase().replace("HR", "H.R.").replace("SJRES", "S.J.Res.").replace("HJRES", "H.J.Res.");

        billInfo.innerHTML = `
            <h3>${typeLabel} ${number} — ${title}</h3>
            <div class="bill-meta">
                ${congress}th Congress · ${chamber} · Policy Area: ${policyArea || "Not assigned"}
            </div>
        `;

        // Fetch actual committees
        const commData = await apiGet(`${baseUrl}/committees`);
        const actualComms = [];
        if (commData && commData.committees) {
            for (const c of commData.committees) {
                actualComms.push(c.name);
            }
        }

        // Fetch subjects for better prediction
        let subjects = [];
        const subjData = await apiGet(`${baseUrl}/subjects`);
        if (subjData && subjData.subjects && subjData.subjects.legislativeSubjects) {
            subjects = subjData.subjects.legislativeSubjects.map(s => s.name);
        }

        // Display actual committees
        if (actualComms.length > 0) {
            actualDiv.innerHTML = actualComms
                .map(c => `<span class="committee-tag actual">${c}</span>`)
                .join("");
        } else {
            actualDiv.innerHTML = "<p>No committee referral recorded yet.</p>";
        }

        // Run prediction
        const predictions = CommitteeModel.predict(title, policyArea, subjects, chamber);
        const predictedNames = predictions.slice(0, 5).map(p => p.committee);

        // Display predicted with match highlighting
        predictedDiv.innerHTML = predictions.slice(0, 5)
            .map(p => {
                const isMatch = actualComms.includes(p.committee);
                const cls = isMatch ? "committee-tag match" : "committee-tag predicted";
                const pct = Math.round(p.confidence * 100);
                return `<span class="${cls}">${p.committee} (${pct}%)${isMatch ? " ✓" : ""}</span>`;
            })
            .join("");

        // Match indicator
        if (actualComms.length > 0) {
            const matches = actualComms.filter(c => predictedNames.includes(c));
            const matchPct = Math.round((matches.length / actualComms.length) * 100);

            let indicator;
            if (matches.length === actualComms.length) {
                indicator = `<div class="match-indicator correct">All ${matches.length} committee(s) correctly predicted</div>`;
            } else if (matches.length > 0) {
                indicator = `<div class="match-indicator partial">${matches.length} of ${actualComms.length} committees matched (${matchPct}%)</div>`;
            } else {
                indicator = `<div class="match-indicator partial">Primary committee not in top-5 predictions</div>`;
            }
            predictedDiv.innerHTML += indicator;
        }

        // Also show the full prediction below
        displayPredictions(predictions);

    } catch (e) {
        billInfo.innerHTML = `<p>Error looking up bill: ${e.message}</p>`;
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
 * Render the pattern chart showing committee distribution.
 */
function renderPatternChart() {
    if (!CommitteeModel.loaded) return;

    const chartDiv = document.getElementById("pattern-chart");
    const commCounts = {};

    for (const bill of dataset) {
        for (const comm of bill.committees) {
            commCounts[comm] = (commCounts[comm] || 0) + 1;
        }
    }

    const sorted = Object.entries(commCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20);

    const maxCount = sorted[0] ? sorted[0][1] : 1;

    let html = '<h3 style="font-size: 1rem; color: var(--primary); margin-bottom: 12px;">Committee Referral Frequency (Training Data)</h3>';
    for (const [name, count] of sorted) {
        const width = Math.round((count / maxCount) * 100);
        html += `
            <div class="chart-bar-group">
                <div class="chart-label" title="${name}">${name}</div>
                <div class="chart-bar" style="width: ${width}%">
                    <span>${count}</span>
                </div>
            </div>
        `;
    }

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
    tbody.innerHTML = page.map(b => `
        <tr>
            <td><a href="https://congress.gov/bill/${b.congress}th-congress/${b.type === 'HR' ? 'house' : 'senate'}-bill/${b.number}" target="_blank">${b.type} ${b.number}</a></td>
            <td>${b.title.substring(0, 80)}${b.title.length > 80 ? "..." : ""}</td>
            <td>${b.policyArea || "—"}</td>
            <td>${b.committees.join(", ")}</td>
        </tr>
    `).join("");

    // Pagination
    const pagDiv = document.getElementById("pagination");
    if (totalPages <= 1) {
        pagDiv.innerHTML = `<span style="color: var(--text-light); font-size: 0.85rem;">${filtered.length} bills</span>`;
        return;
    }

    let pagHtml = "";
    if (datasetPage > 0) {
        pagHtml += `<button onclick="changePage(${datasetPage - 1})">← Prev</button>`;
    }
    pagHtml += `<span style="padding: 6px 12px; font-size: 0.85rem; color: var(--text-light);">Page ${datasetPage + 1} of ${totalPages} (${filtered.length} bills)</span>`;
    if (datasetPage < totalPages - 1) {
        pagHtml += `<button onclick="changePage(${datasetPage + 1})">Next →</button>`;
    }
    pagDiv.innerHTML = pagHtml;
}

function changePage(page) {
    datasetPage = page;
    renderDataset();
}

function filterDataset() {
    datasetPage = 0;
    renderDataset();
}
