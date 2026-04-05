/**
 * Tip Jar — Frontend logic (tabbed UI).
 *
 * Uses the @dfinity/agent library to call the backend canister.
 * CDN imports keep the template dependency-free.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const IS_LOCAL = window.location.hostname === "localhost"
              || window.location.hostname === "127.0.0.1";

const IC_HOST = IS_LOCAL ? "http://localhost:4943" : "https://ic0.app";

let BACKEND_CANISTER_ID = "k5ony-gyaaa-aaaam-aityq-cai";

async function detectBackendCanisterId() {
  if (BACKEND_CANISTER_ID && !BACKEND_CANISTER_ID.startsWith("__")) {
    return BACKEND_CANISTER_ID;
  }
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("canisterId") || params.get("backendId");
  if (fromUrl) { BACKEND_CANISTER_ID = fromUrl; return BACKEND_CANISTER_ID; }
  if (BACKEND_CANISTER_ID.startsWith("__")) {
    const el = document.getElementById("canister-id");
    if (el) {
      el.innerHTML = 'Backend canister ID not configured.';
      el.style.color = "#dc2626";
    }
  }
  return BACKEND_CANISTER_ID;
}

// ---------------------------------------------------------------------------
// Candid IDL factory
// ---------------------------------------------------------------------------

function idlFactory({ IDL }) {
  return IDL.Service({
    get_leaderboard:     IDL.Func([], [IDL.Text], ["query"]),
    get_donor_messages:  IDL.Func([IDL.Text], [IDL.Text], ["query"]),
    get_messages:        IDL.Func([IDL.Nat64], [IDL.Text], ["query"]),
    get_stats:           IDL.Func([], [IDL.Text], ["query"]),
    status:              IDL.Func([], [IDL.Text], ["query"]),
    get_time:            IDL.Func([], [IDL.Nat64], ["query"]),
    whoami:              IDL.Func([], [IDL.Text], ["query"]),
    read_secret_notes:   IDL.Func([], [IDL.Text], ["query"]),
    register_tip:        IDL.Func([IDL.Text, IDL.Nat64, IDL.Text, IDL.Text], [IDL.Text], []),
    verify_tip:          IDL.Func([IDL.Nat64], [IDL.Text], []),
    check_balance:       IDL.Func([IDL.Text], [IDL.Text], []),
    refresh_fx:          IDL.Func([], [IDL.Text], []),
  });
}

// ---------------------------------------------------------------------------
// Agent & Actor
// ---------------------------------------------------------------------------

let actor = null;
let authClient = null;
let _agentModule = null;

async function loadAgentModule() {
  if (_agentModule) return _agentModule;
  _agentModule = await import("https://esm.sh/@dfinity/agent@2.2.0");
  return _agentModule;
}

async function loadAuthClient() {
  if (authClient) return authClient;
  const { AuthClient } = await import("https://esm.sh/@dfinity/auth-client@2.2.0?deps=@dfinity/agent@2.2.0,@dfinity/candid@2.2.0,@dfinity/identity@2.2.0");
  authClient = await AuthClient.create();
  return authClient;
}

async function buildActor(identity) {
  const canisterId = await detectBackendCanisterId();
  if (canisterId.startsWith("__")) throw new Error("Backend canister ID not configured.");
  const { HttpAgent, Actor } = await loadAgentModule();
  const opts = { host: IC_HOST };
  if (identity) opts.identity = identity;
  const agent = await HttpAgent.create(opts);
  if (IS_LOCAL) await agent.fetchRootKey();
  return Actor.createActor(idlFactory, { agent, canisterId });
}

async function getActor() {
  if (actor) return actor;
  actor = await buildActor();
  return actor;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function $(id) { return document.getElementById(id); }
function setStatus(msg) { const el = $("tip-status"); if (el) el.textContent = msg; }
function setInfo(msg) { const el = $("info-output"); if (el) el.textContent = msg; }
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

function truncPrincipal(p) {
  if (!p || p.length < 20) return p || "";
  return p.slice(0, 5) + "…" + p.slice(-3);
}

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

window.switchTab = function (btn) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  btn.classList.add("active");
  const panel = $(btn.dataset.tab);
  if (panel) panel.classList.add("active");
};

// ---------------------------------------------------------------------------
// Leaderboard — paginated, expandable rows
// ---------------------------------------------------------------------------

const PAGE_SIZE = 10;
let leaderboardData = [];
let currentPage = 0;

async function fetchLeaderboard() {
  try {
    const a = await getActor();
    const raw = await a.get_leaderboard();
    leaderboardData = JSON.parse(raw);
    currentPage = 0;
    renderLeaderboardPage();
  } catch (e) {
    console.error("fetchLeaderboard:", e);
  }
}

function renderLeaderboardPage() {
  const tbody = $("leaderboard-body");
  if (!leaderboardData.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">No donors yet</td></tr>';
    $("leaderboard-pager").innerHTML = "";
    return;
  }

  const totalPages = Math.ceil(leaderboardData.length / PAGE_SIZE);
  const start = currentPage * PAGE_SIZE;
  const page = leaderboardData.slice(start, start + PAGE_SIZE);

  tbody.innerHTML = page.map((r, i) => {
    const rank = start + i + 1;
    const rowId = `donor-row-${rank}`;
    return `<tr class="donor-row" data-donor="${esc(r.name)}" onclick="toggleDonorMessages(this, '${esc(r.name).replace(/'/g, "\\'")}')">
      <td>${rank}</td>
      <td>${esc(r.name)}</td>
      <td class="mono" title="${esc(r.principal)}">${truncPrincipal(r.principal)}</td>
      <td>${r.total_donated.toLocaleString()}</td>
      <td>${r.message_count}</td>
    </tr>
    <tr id="${rowId}" class="donor-messages-row" style="display:none">
      <td colspan="5"><div class="donor-messages-container">Loading…</div></td>
    </tr>`;
  }).join("");

  // Pager
  const pager = $("leaderboard-pager");
  if (totalPages <= 1) { pager.innerHTML = ""; return; }
  let html = "";
  if (currentPage > 0) html += `<button onclick="leaderboardPage(${currentPage - 1})">&laquo; Prev</button>`;
  html += `<span class="pager-info">Page ${currentPage + 1} / ${totalPages}</span>`;
  if (currentPage < totalPages - 1) html += `<button onclick="leaderboardPage(${currentPage + 1})">Next &raquo;</button>`;
  pager.innerHTML = html;
}

window.leaderboardPage = function (page) {
  currentPage = page;
  renderLeaderboardPage();
};

window.toggleDonorMessages = async function (rowEl, donorName) {
  const rank = rowEl.querySelector("td").textContent;
  const msgRow = $(`donor-row-${rank}`);
  if (!msgRow) return;

  if (msgRow.style.display !== "none") {
    msgRow.style.display = "none";
    return;
  }

  msgRow.style.display = "table-row";
  const container = msgRow.querySelector(".donor-messages-container");
  container.innerHTML = "Loading…";

  try {
    const a = await getActor();
    const raw = await a.get_donor_messages(donorName);
    const msgs = JSON.parse(raw);

    if (!msgs.length) {
      container.innerHTML = '<p class="empty">No messages</p>';
      return;
    }

    container.innerHTML = msgs.map(m => {
      const isSecret = m.type === "secret";
      const badge = m.amount ? `<span class="badge">${m.amount.toLocaleString()} sats</span>` : "";
      const icon = isSecret ? '<span class="badge badge-secret">encrypted</span>' : "";
      const text = isSecret
        ? `<code class="encrypted-text">${esc(m.message).slice(0, 60)}…</code>`
        : (m.message ? `<p>${esc(m.message)}</p>` : "");
      const time = m.timestamp ? `<time>${new Date(m.timestamp * 1000).toLocaleString()}</time>` : "";
      return `<div class="message">${badge}${icon}${text}${time}</div>`;
    }).join("");
  } catch (e) {
    container.innerHTML = `<p class="empty">Error: ${e.message}</p>`;
  }
};

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

async function fetchStats() {
  try {
    const a = await getActor();
    const raw = await a.get_stats();
    const s = JSON.parse(raw);
    $("stat-donors").textContent = s.donor_count ?? "—";
    $("stat-messages").textContent = s.message_count ?? "—";
    $("stat-total").textContent = (s.total_donated_satoshis ?? 0).toLocaleString();
    $("stat-btc-usd").textContent = s.btc_usd
      ? `$${Number(s.btc_usd).toLocaleString()}`
      : "—";
    const updEl = $("stat-btc-updated");
    if (updEl && s.fx_last_updated) {
      const d = new Date(s.fx_last_updated * 1000);
      updEl.textContent = `Updated ${d.toLocaleString()}`;
    } else if (updEl) {
      updEl.textContent = "";
    }
  } catch (e) {
    console.error("fetchStats:", e);
  }
}

// ---------------------------------------------------------------------------
// Donate flow
// ---------------------------------------------------------------------------

let currentPendingId = null;

function showDonateStep(n) {
  for (let i = 1; i <= 4; i++) {
    const el = $("donate-step-" + i);
    if (!el) continue;
    el.classList.remove("step-disabled", "step-locked");
    if (i < n) {
      el.classList.add("step-locked");
    } else if (i > n) {
      el.classList.add("step-disabled");
    }
  }
}
window.showDonateStep = showDonateStep;

window.registerTip = async function () {
  const name = $("input-name").value.trim();
  const amount = parseInt($("input-amount").value || "0", 10);
  const message = $("input-message").value.trim();
  const msgType = $("input-msg-private")?.checked ? "secret" : "public";

  if (!name) return setStatus("Enter your nickname.");
  if (amount <= 0) return setStatus("Enter an amount.");

  setStatus("Registering tip...");
  try {
    const a = await getActor();
    const raw = await a.register_tip(name, BigInt(amount), message, msgType);
    const res = JSON.parse(raw);
    if (res.error) return setStatus("Error: " + res.error);

    currentPendingId = res.pending_id;
    $("send-amount").textContent = amount.toLocaleString();
    showDonateStep(3);
    setStatus("");
  } catch (e) {
    setStatus("Error: " + e.message);
  }
};

window.verifyTip = async function () {
  if (!currentPendingId) return setStatus("No pending tip. Start from step 1.");

  const btn = $("btn-verify");
  const origLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Verifying…";
  setStatus("Scanning blockchain for your transfer…");
  try {
    const a = await getActor();
    const raw = await a.verify_tip(BigInt(currentPendingId));
    const res = JSON.parse(raw);

    if (res.status === "not_found") {
      setStatus(res.message);
      btn.disabled = false;
      btn.textContent = origLabel;
      return;
    }
    if (res.error) {
      setStatus("Error: " + res.error);
      btn.disabled = false;
      btn.textContent = origLabel;
      return;
    }

    currentPendingId = null;
    showDonateStep(4);
    $("verified-donor").textContent = res.donor;
    $("verified-amount").textContent = Number(res.amount).toLocaleString();
    $("verified-tx").textContent = res.tx_id;
    setStatus("");
    await refreshAll();
  } catch (e) {
    setStatus("Error: " + e.message);
    btn.disabled = false;
    btn.textContent = origLabel;
  }
};

window.resetTipFlow = function () {
  currentPendingId = null;
  $("input-name").value = "";
  $("input-amount").value = "1000";
  $("input-message").value = "";
  showDonateStep(1);
  setStatus("");
};

// ---------------------------------------------------------------------------
// More tab actions
// ---------------------------------------------------------------------------

window.callWhoami = async function () {
  try { const a = await getActor(); setInfo(await a.whoami()); }
  catch (e) { setInfo("Error: " + e.message); }
};

window.callStatus = async function () {
  try { const a = await getActor(); setInfo(await a.status()); }
  catch (e) { setInfo("Error: " + e.message); }
};

window.callTime = async function () {
  try {
    const a = await getActor();
    const ns = await a.get_time();
    const date = new Date(Number(ns / BigInt(1_000_000)));
    setInfo(`${ns} ns\n${date.toISOString()}`);
  } catch (e) { setInfo("Error: " + e.message); }
};

window.refreshAll = async function () {
  await Promise.all([fetchStats(), fetchLeaderboard()]);
  // Fire-and-forget: refresh FX rate in the background, then update stats
  getActor().then(a => a.refresh_fx()).then(() => fetchStats()).catch(() => {});
};

// ---------------------------------------------------------------------------
// Internet Identity
// ---------------------------------------------------------------------------

const II_URL = IS_LOCAL
  ? `http://localhost:4943?canisterId=rdmx6-jaaaa-aaaaa-aaadq-cai`
  : "https://identity.ic0.app";

function updateAuthUI(isLoggedIn, principal) {
  const btn = $("btn-login");
  const info = $("auth-principal");
  if (btn) btn.textContent = isLoggedIn ? "Logout" : "Login with Internet Identity";
  if (info) info.textContent = isLoggedIn ? principal : "";

  // Also update the donate tab step 1
  const donateBtn = $("btn-donate-login");
  const donateStatus = $("donate-auth-status");
  if (isLoggedIn) {
    if (donateBtn) donateBtn.textContent = "Logged in ✓";
    if (donateStatus) donateStatus.textContent = `Principal: ${principal}`;
    // Auto-advance to step 2
    showDonateStep(2);
  } else {
    if (donateBtn) donateBtn.textContent = "Login with Internet Identity";
    if (donateStatus) donateStatus.textContent = "";
  }
}

async function checkAuth() {
  try {
    const client = await loadAuthClient();
    const isAuth = await client.isAuthenticated();
    if (isAuth) {
      const identity = client.getIdentity();
      const principal = identity.getPrincipal().toText();
      actor = await buildActor(identity);
      updateAuthUI(true, principal);
    } else {
      updateAuthUI(false);
    }
  } catch (e) {
    console.error("checkAuth:", e);
  }
}

window.toggleLogin = async function () {
  const client = await loadAuthClient();
  const isAuth = await client.isAuthenticated();
  if (isAuth) {
    await client.logout();
    actor = null;
    actor = await buildActor();
    updateAuthUI(false);
    return;
  }
  await new Promise((resolve, reject) => {
    client.login({
      identityProvider: II_URL,
      maxTimeToLive: BigInt(8) * BigInt(3_600_000_000_000),
      onSuccess: resolve,
      onError: reject,
    });
  });
  const identity = client.getIdentity();
  const principal = identity.getPrincipal().toText();
  actor = await buildActor(identity);
  updateAuthUI(true, principal);
  await refreshAll();
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

(async function boot() {
  const ft = $("footer-time");
  if (ft) ft.textContent = new Date().toISOString().replace("T", " ").slice(0, 19) + "Z";

  const cid = await detectBackendCanisterId();
  if (!cid.startsWith("__")) {
    $("canister-id").textContent = `Backend: ${cid}`;
    const addrEl = $("canister-address");
    if (addrEl) addrEl.textContent = cid;
    await checkAuth();
    await refreshAll();
  }
})();
