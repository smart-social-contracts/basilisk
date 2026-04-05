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
let BACKEND_CANISTER_ID = "__BACKEND_CANISTER_ID__";

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
    register_donor:      IDL.Func([IDL.Text], [IDL.Text], []),
    leave_message:       IDL.Func([IDL.Text, IDL.Text], [IDL.Text], []),
    tip:                 IDL.Func([IDL.Text, IDL.Text, IDL.Nat64, IDL.Text], [IDL.Text], []),
    submit_secret_note:  IDL.Func([IDL.Text, IDL.Text], [IDL.Text], []),
    check_balance:       IDL.Func([IDL.Text], [IDL.Text], []),
    refresh_fx:          IDL.Func([], [IDL.Text], []),
  });
}

// ---------------------------------------------------------------------------
// Agent & Actor setup
// ---------------------------------------------------------------------------

let actor = null;

async function getActor() {
  if (actor) return actor;

  const canisterId = await detectBackendCanisterId();
  if (canisterId.startsWith("__")) {
    throw new Error("Backend canister ID not configured. See app.js.");
  }

  // Dynamically import @dfinity/agent from CDN (keeps template dependency-free)
  const { HttpAgent, Actor } = await import(
    "https://esm.sh/@dfinity/agent@2.2.0"
  );

  const agent = await HttpAgent.create({ host: IC_HOST });

  // When running locally, fetch the root key (not needed on mainnet)
  if (IS_LOCAL) {
    await agent.fetchRootKey();
  }

  actor = Actor.createActor(idlFactory, {
    agent,
    canisterId,
  });
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

window.registerDonor = async function () {
  const name = $("input-name").value.trim();
  if (!name) return setStatus("Enter a name first.");
  setStatus("Registering...");
  try {
    const a = await getActor();
    const raw = await a.register_donor(name);
    const res = JSON.parse(raw);
    setStatus(res.status === "created" ? `Registered "${name}"!` : `"${name}" already exists.`);
    await refreshAll();
  } catch (e) {
    setStatus("Error: " + e.message);
  }
};

window.submitTip = async function () {
  const name = $("input-name").value.trim();
  const amount = parseInt($("input-amount").value || "0", 10);
  const token = $("input-token").value;
  const message = $("input-message").value.trim();
  if (!name) return setStatus("Enter your name first.");
  if (!message) return setStatus("Write a message!");

  setStatus("Recording tip...");
  try {
    const a = await getActor();
    const raw = await a.tip(name, token, BigInt(amount), message);
    const res = JSON.parse(raw);
    if (res.error) {
      setStatus("Error: " + res.error);
    } else {
      setStatus(`Tip recorded! New total: ${res.new_total.toLocaleString()} sats`);
      $("input-message").value = "";
      await refreshAll();
    }
  } catch (e) {
    setStatus("Error: " + e.message);
  }
};

window.submitSecretNote = async function () {
  const name = $("note-name").value.trim();
  const text = $("note-text").value.trim();
  if (!name) return setNoteStatus("Enter your name.");
  if (!text) return setNoteStatus("Write a note!");

  setNoteStatus("Encrypting & sending...");
  try {
    const a = await getActor();
    const raw = await a.submit_secret_note(name, text);
    const res = JSON.parse(raw);
    if (res.error) {
      setNoteStatus("Error: " + res.error);
    } else {
      setNoteStatus("Secret note sent! Only the owner can read it.");
      $("note-text").value = "";
    }
  } catch (e) {
    setNoteStatus("Error: " + e.message);
  }
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
// Boot
// ---------------------------------------------------------------------------

(async function boot() {
  // Detect backend canister ID
  const cid = await detectBackendCanisterId();
  if (!cid.startsWith("__")) {
    $("canister-id").textContent = `Backend: ${cid}`;
    // Show the canister address in the Oisy instructions
    const addrEl = $("canister-address");
    if (addrEl) addrEl.textContent = cid;
    // Load initial data
    await refreshAll();
  }
})();
