const basePath = document.body?.dataset?.base || "";
const apiUrl = (path) => `${basePath}${path}`;

const state = {
    leaderboard: [],
    battle: null,
    locked: false,
    totalVotes: 0,
};

const leaderboardBody = document.getElementById("leaderboardBody");
const benchmarkCopy = document.getElementById("benchmarkCopy");
const categoryPill = document.getElementById("categoryPill");
const jokeCardsWrapper = document.getElementById("jokeCards");
const progressPill = document.getElementById("progressPill");
const progressFill = progressPill?.querySelector(".progress-bar span");
const totalVotesEl = document.getElementById("totalVotes");

async function loadLeaderboard() {
    try {
        const response = await fetch(apiUrl("/api/leaderboard"));
        if (!response.ok) throw new Error("Failed to load leaderboard");
        const data = await response.json();
        state.leaderboard = data.leaderboard ?? [];
        state.totalVotes = data.total_votes ?? state.totalVotes;
        totalVotesEl.textContent = formatNumber(state.totalVotes);
        benchmarkCopy.textContent = data.explanation ?? "";
        renderLeaderboard();
    } catch (error) {
        leaderboardBody.innerHTML = `<tr><td colspan="4">Could not load leaderboard.</td></tr>`;
        totalVotesEl.textContent = "—";
    }
}

function renderLeaderboard() {
    if (!state.leaderboard.length) {
        leaderboardBody.innerHTML = `<tr><td colspan="4">No data yet.</td></tr>`;
        return;
    }
    leaderboardBody.innerHTML = state.leaderboard
        .map(
            (entry) => `
            <tr>
                <td>${entry.rank}</td>
                <td>${entry.model}</td>
                <td>${formatNumber(entry.votes ?? 0)}</td>
                <td>${entry.elo}</td>
            </tr>
        `
        )
        .join("");
}

async function loadBattle() {
    try {
        const response = await fetch(apiUrl("/api/battle"));
        if (!response.ok) throw new Error("Failed to load battle");
        const data = await response.json();
        state.battle = data;
        state.locked = false;
        renderBattle();
        hideAdvanceBanner();
    } catch (error) {
        jokeCardsWrapper.innerHTML =
            '<button class="joke-card placeholder">Unable to fetch battle.</button>';
    }
}

function renderBattle() {
    if (!state.battle) return;
    const { category, contestants } = state.battle;
    categoryPill.textContent = category;
    jokeCardsWrapper.innerHTML = "";
    contestants.forEach((contestant, idx) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "joke-card";
        button.dataset.id = contestant.id;
        button.dataset.rank = contestant.rank;
        button.dataset.index = idx;
        button.dataset.model = contestant.id;
        button.dataset.side = idx === 0 ? "A" : "B";
        button.innerHTML = `
            <div class="card-header">
                <span class="assistant-label">Model ${button.dataset.side}</span>
            </div>
            <div class="joke-text">${contestant.joke.replace(/\n/g, "<br>")}</div>
        `;
        button.addEventListener("click", handleVote);
        jokeCardsWrapper.appendChild(button);
    });
}

async function handleVote(event) {
    if (state.locked || !state.battle) return;
    state.locked = true;
    const button = event.currentTarget;
    const winnerId = button.dataset.id;
    revealModels(winnerId);
    disableCards();
    showAdvanceBanner();

    try {
        const response = await fetch(apiUrl("/api/battle_result"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ battle_id: state.battle.battle_id, winner: winnerId }),
        });
        if (response.ok) {
            const data = await response.json();
            state.leaderboard = data.leaderboard ?? [];
            state.totalVotes = data.total_votes ?? state.totalVotes;
            totalVotesEl.textContent = formatNumber(state.totalVotes);
            renderLeaderboard();
        }
    } catch (error) {
        // Ignore, banner text already shows progress
    } finally {
        setTimeout(() => {
            loadBattle();
        }, 5000);
    }
}

function revealModels(selectedId) {
    document.querySelectorAll(".joke-card").forEach((card) => {
        const label = card.querySelector(".assistant-label");
        if (!label) return;
        const model = card.dataset.model ?? "Unknown";
        label.textContent = model;
        label.classList.add("revealed");
        card.classList.add("revealed");
        card.classList.toggle("selected", card.dataset.model === selectedId);
    });
}

function disableCards() {
    document.querySelectorAll(".joke-card").forEach((card) => {
        card.classList.add("disabled");
        card.disabled = true;
    });
}

function showAdvanceBanner() {
    if (!progressPill || !progressFill) return;
    progressPill.classList.add("active");
    progressPill.setAttribute("aria-hidden", "false");
    progressFill.style.width = "0%";
    // Force a reflow to restart the transition
    void progressFill.offsetWidth;
    progressFill.style.width = "100%";
}

function hideAdvanceBanner() {
    if (!progressPill || !progressFill) return;
    progressPill.classList.remove("active");
    progressPill.setAttribute("aria-hidden", "true");
    progressFill.style.width = "0%";
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString();
}

function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            const target = tab.dataset.target;
            if (!target) return;
            tabs.forEach((btn) => btn.classList.remove("active"));
            document.querySelectorAll(".panel").forEach((panel) => panel.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById(target)?.classList.add("active");
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    setupTabs();
    loadLeaderboard();
    loadBattle();
});
