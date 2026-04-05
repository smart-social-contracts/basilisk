/**
 * Tip Jar — Frontend logic.
 *
 * Uses the @dfinity/agent library to call the backend canister.
 * For local development (dfx start), the agent connects to
 * http://localhost:4943.  On mainnet it auto-detects the IC gateway.
 *
 * NOTE: This is a minimal example.  A production app would use a
 * bundler (Vite, webpack) and install @dfinity/agent via npm.
 * Here we use dynamic imports from a CDN to keep the template
 * dependency-free.
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const IS_LOCAL = window.location.hostname === "localhost"
              || window.location.hostname === "127.0.0.1";

const IC_HOST = IS_LOCAL ? "http://localhost:4943" : "https://ic0.app";

// Backend canister ID — detected automatically.
// Local dev:  fetches /.well-known/canister-ids from the asset canister
//             (dfx v0.24+ serves this), or falls back to the placeholder.
// Mainnet:    replace the placeholder below after `dfx deploy --network ic`.
let BACKEND_CANISTER_ID = "k5ony-gyaaa-aaaam-aityq-cai";

async function detectBackendCanisterId() {
  // 1. Already set to a real principal (not placeholder)
  if (BACKEND_CANISTER_ID && !BACKEND_CANISTER_ID.startsWith("__")) {
    return BACKEND_CANISTER_ID;
  }

  // 2. Check URL query params: ?backendId=<canister-id>
  //    After `dfx deploy`, open:
  //    http://<frontend-id>.localhost:4943?backendId=<backend-id>
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("canisterId") || params.get("backendId");
  if (fromUrl) {
    BACKEND_CANISTER_ID = fromUrl;
    return BACKEND_CANISTER_ID;
  }

  // 3. Prompt the user if we still don't have it
  if (BACKEND_CANISTER_ID.startsWith("__")) {
    const el = document.getElementById("canister-id");
    if (el) {
      el.innerHTML =
        'Backend canister ID not configured. After <code>dfx deploy</code>, ' +
        'add <code>?backendId=&lt;BACKEND_CANISTER_ID&gt;</code> to the URL, ' +
        'or edit <code>BACKEND_CANISTER_ID</code> in <code>app.js</code>.';
      el.style.color = "#dc2626";
    }
  }

  return BACKEND_CANISTER_ID;
}

// ---------------------------------------------------------------------------
// Candid IDL factory (matches the backend endpoints)
// ---------------------------------------------------------------------------

// Minimal IDL factory — we only use text/nat64 args and text returns,
// so we can define it inline without importing the full .did.js file.
function idlFactory({ IDL }) {
  return IDL.Service({
    // Queries
    get_leaderboard:     IDL.Func([], [IDL.Text], ["query"]),
    get_messages:        IDL.Func([IDL.Nat64], [IDL.Text], ["query"]),
    get_stats:           IDL.Func([], [IDL.Text], ["query"]),
    status:              IDL.Func([], [IDL.Text], ["query"]),
    get_time:            IDL.Func([], [IDL.Nat64], ["query"]),
    whoami:              IDL.Func([], [IDL.Text], ["query"]),
    read_secret_notes:   IDL.Func([], [IDL.Text], ["query"]),
    // Updates
    register_tip:        IDL.Func([IDL.Text, IDL.Nat64, IDL.Text, IDL.Text], [IDL.Text], []),
    verify_tip:          IDL.Func([IDL.Nat64], [IDL.Text], []),
    check_balance:       IDL.Func([IDL.Text], [IDL.Text], []),
    refresh_fx:          IDL.Func([], [IDL.Text], []),
  });
}

// ---------------------------------------------------------------------------
// Agent & Actor setup (with optional Internet Identity auth)
// ---------------------------------------------------------------------------

let actor = null;
let authClient = null;
let _agentModule = null;  // cached @dfinity/agent module

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
  if (canisterId.startsWith("__")) {
    throw new Error("Backend canister ID not configured. See app.js.");
  }
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
// UI Helpers
// ---------------------------------------------------------------------------

function $(id) { return document.getElementById(id); }

function setStatus(msg) {
  const el = $("tip-status");
  if (el) el.textContent = msg;
}

function setNoteStatus(msg) {
  const el = $("note-status");
  if (el) el.textContent = msg;
}

function setInfo(msg) {
  const el = $("info-output");
  if (el) el.textContent = msg;
}

// ---------------------------------------------------------------------------
// Data fetchers
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
    // Show FX last-updated time
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

async function fetchLeaderboard() {
  try {
    const a = await getActor();
    const raw = await a.get_leaderboard();
    const rows = JSON.parse(raw);
    const tbody = $("leaderboard-body");
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">No donors yet</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((r, i) =>
        `<tr>
          <td>${i + 1}</td>
          <td>${esc(r.name)}</td>
          <td>${r.total_donated.toLocaleString()}</td>
          <td>${r.usd_value != null ? "$" + r.usd_value : "—"}</td>
          <td>${r.message_count}</td>
        </tr>`
      )
      .join("");
  } catch (e) {
    console.error("fetchLeaderboard:", e);
  }
}

async function fetchMessages() {
  try {
    const a = await getActor();
    const raw = await a.get_messages(BigInt(20));
    const msgs = JSON.parse(raw);
    const el = $("messages-list");
    if (!msgs.length) {
      el.innerHTML = '<p class="empty">No messages yet</p>';
      return;
    }
    el.innerHTML = msgs
      .map(
        (m) =>
          `<div class="message">
            <strong>${esc(m.donor)}</strong>
            ${m.amount ? `<span class="badge">${m.amount.toLocaleString()} sats</span>` : ""}
            <p>${esc(m.message)}</p>
            <time>${new Date(m.timestamp * 1000).toLocaleString()}</time>
          </div>`
      )
      .join("");
  } catch (e) {
    console.error("fetchMessages:", e);
  }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Tip flow state
// ---------------------------------------------------------------------------

let currentPendingId = null;

function showStep(n) {
  for (let i = 1; i <= 3; i++) {
    const el = $("tip-step-" + i);
    if (el) el.style.display = i === n ? "block" : "none";
  }
}

window.registerTip = async function () {
  const name = $("input-name").value.trim();
  const amount = parseInt($("input-amount").value || "0", 10);
  const message = $("input-message").value.trim();
  const msgType = $("input-msg-type").value || "public";

  if (!name) return setStatus("Enter your name.");
  if (amount <= 0) return setStatus("Enter an amount.");

  setStatus("Registering tip...");
  try {
    const a = await getActor();
    const raw = await a.register_tip(name, BigInt(amount), message, msgType);
    const res = JSON.parse(raw);
    if (res.error) return setStatus("Error: " + res.error);

    currentPendingId = res.pending_id;
    // Show step 2 with the amount they need to send
    $("send-amount").textContent = amount.toLocaleString();
    showStep(2);
    setStatus("");
  } catch (e) {
    setStatus("Error: " + e.message);
  }
};

window.verifyTip = async function () {
  if (!currentPendingId) return setStatus("No pending tip. Start from step 1.");

  setStatus("Scanning blockchain for your transfer...");
  $("btn-verify").disabled = true;
  try {
    const a = await getActor();
    const raw = await a.verify_tip(BigInt(currentPendingId));
    const res = JSON.parse(raw);

    if (res.status === "not_found") {
      setStatus(res.message);
      $("btn-verify").disabled = false;
      return;
    }
    if (res.error) {
      setStatus("Error: " + res.error);
      $("btn-verify").disabled = false;
      return;
    }

    // Success!
    currentPendingId = null;
    showStep(3);
    $("verified-donor").textContent = res.donor;
    $("verified-amount").textContent = Number(res.amount).toLocaleString();
    $("verified-tx").textContent = res.tx_id;
    setStatus("");
    await refreshAll();
  } catch (e) {
    setStatus("Error: " + e.message);
    $("btn-verify").disabled = false;
  }
};

window.resetTipFlow = function () {
  currentPendingId = null;
  $("input-name").value = "";
  $("input-amount").value = "1000";
  $("input-message").value = "";
  showStep(1);
  setStatus("");
};

window.callWhoami = async function () {
  try {
    const a = await getActor();
    setInfo(await a.whoami());
  } catch (e) { setInfo("Error: " + e.message); }
};

window.callStatus = async function () {
  try {
    const a = await getActor();
    setInfo(await a.status());
  } catch (e) { setInfo("Error: " + e.message); }
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
  await Promise.all([fetchStats(), fetchLeaderboard(), fetchMessages()]);
};

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ---------------------------------------------------------------------------
// Internet Identity login / logout
// ---------------------------------------------------------------------------

const II_URL = IS_LOCAL
  ? `http://localhost:4943?canisterId=rdmx6-jaaaa-aaaaa-aaadq-cai`
  : "https://identity.ic0.app";

function updateAuthUI(isLoggedIn, principal) {
  const btn = $("btn-login");
  const info = $("auth-principal");
  if (btn) btn.textContent = isLoggedIn ? "Logout" : "Login with Internet Identity";
  if (info) info.textContent = isLoggedIn ? `Logged in as ${principal}` : "";
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
  } else {
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
  }
};

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

(async function boot() {
  // Footer timestamp
  const ft = $("footer-time");
  if (ft) ft.textContent = new Date().toISOString().replace("T", " ").slice(0, 19) + "Z";

  // Detect backend canister ID
  const cid = await detectBackendCanisterId();
  if (!cid.startsWith("__")) {
    $("canister-id").textContent = `Backend: ${cid}`;
    // Show the canister address in the Oisy instructions
    const addrEl = $("canister-address");
    if (addrEl) addrEl.textContent = cid;
    // Check for existing II session
    await checkAuth();
    // Load initial data
    await refreshAll();
  }
})();
