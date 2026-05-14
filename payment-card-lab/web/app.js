// Payment Card Lab — frontend.
// Hace fetch directo al mismo origen (api.py sirve el HTML y el JSON).

const $ = (sel) => document.querySelector(sel);
const state = { card: null, account_id: null, dpan: null };

// --- helpers --------------------------------------------------------
async function api(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

function toast(msg, kind = "") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = kind;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 4500);
}

function fmtMoney(minor, ccy = "MXN") {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: ccy })
    .format(minor / 100);
}

function fmtPan(pan) {
  return pan.match(/.{1,4}/g).join("  ");
}

// --- health ---------------------------------------------------------
async function checkHealth() {
  try {
    const h = await api("GET", "/health");
    $("#health-pill").textContent = `api · BIN ${h.issuer_bin}`;
    $("#health-pill").className = "pill ok";
  } catch (e) {
    $("#health-pill").textContent = "api: offline";
    $("#health-pill").className = "pill err";
  }
}

// --- emitir tarjeta -------------------------------------------------
async function issueCard() {
  $("#btn-issue").disabled = true;
  try {
    const holder = await api("POST", "/holders", {
      full_name: $("#holder-name").value,
      country: $("#holder-country").value || "MX",
    });
    const acc = await api("POST", "/accounts", {
      holder_id: holder.holder_id,
      type: $("#acct-type").value,
      initial_deposit_minor: Math.round(parseFloat($("#deposit").value) * 100),
      currency: "MXN",
    });
    state.account_id = acc.account_id;
    const card = await api("POST", "/cards", { account_id: acc.account_id });
    state.card = card;

    $("#card-pan").textContent = fmtPan(card.pan);
    $("#card-exp").textContent = card.expiry;
    $("#card-cvv").textContent = card.cvv;
    $("#card-holder").textContent = $("#holder-name").value.toUpperCase();
    $("#m-psn").textContent = card.psn;
    $("#m-acct").textContent = acc.account_id;
    $("#card-wrap").hidden = false;

    await refreshBalance();
    $("#btn-charge").disabled = false;
    $("#btn-provision").disabled = false;
    toast("Tarjeta emitida. Datos visibles en el panel.", "success");
    await loadTxns();
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    $("#btn-issue").disabled = false;
  }
}

async function refreshBalance() {
  if (!state.account_id) return;
  const acc = await api("GET", `/accounts/${state.account_id}`);
  $("#m-posted").textContent = fmtMoney(acc.posted_minor, acc.currency);
  $("#m-held").textContent   = fmtMoney(acc.held_minor, acc.currency);
  $("#m-avail").textContent  = fmtMoney(acc.available_minor, acc.currency);
}

// --- cobrar ---------------------------------------------------------
async function charge() {
  if (!state.card) return;
  $("#btn-charge").disabled = true;
  try {
    const amount_minor = Math.round(parseFloat($("#amount").value) * 100);
    const pos = $("#pos").value;
    let resp = await api("POST", "/authorize", {
      pan: state.card.pan, expiry: state.card.expiry, cvv: state.card.cvv,
      amount_minor, pos_entry: pos, mcc: $("#mcc").value,
    });

    // Si requiere 3DS, resolvemos el challenge automaticamente.
    if (resp.rc === "1A" && resp.threeds) {
      toast(`3DS requerido. OTP demo: ${resp.threeds.otp_demo} — verificando...`);
      const ver = await api("POST", "/threeds/verify", {
        challenge_id: resp.threeds.challenge_id,
        otp: resp.threeds.otp_demo,
      });
      if (!ver.success) throw new Error("3DS fallo: " + ver.reason);
      resp = await api("POST", "/authorize", {
        pan: state.card.pan, expiry: state.card.expiry, cvv: state.card.cvv,
        amount_minor, pos_entry: "ecommerce", mcc: $("#mcc").value,
        cavv: ver.cavv, cavv_cid: resp.threeds.challenge_id,
      });
    }
    if (resp.approved) {
      toast(`✓ Aprobada · RC=${resp.rc} · auth ${resp.auth_code} · ${fmtMoney(amount_minor)}`, "success");
    } else {
      toast(`✗ Rechazada · RC=${resp.rc} · ${resp.message}`, "error");
    }
    await refreshBalance();
    await loadTxns();
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    $("#btn-charge").disabled = false;
  }
}

// --- wallet ---------------------------------------------------------
async function provision() {
  if (!state.card) return;
  $("#btn-provision").disabled = true;
  try {
    const r = await api("POST", "/wallet/provision", {
      pan: state.card.pan, expiry: state.card.expiry, cvv: state.card.cvv,
      device_id: "browser-demo", provider: $("#wallet-provider").value,
    });
    state.dpan = r.dpan;
    $("#dpan").value = r.dpan;
    $("#btn-tap").disabled = false;
    toast("Wallet provisionado · DPAN " + r.dpan, "success");
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    $("#btn-provision").disabled = false;
  }
}

async function tap() {
  if (!state.dpan) return;
  $("#btn-tap").disabled = true;
  try {
    const amount_minor = Math.round(parseFloat($("#tap-amount").value) * 100);
    const r = await api("POST", "/wallet/tap", {
      dpan: state.dpan, expiry: state.card.expiry,
      amount_minor,
    });
    if (r.approved) {
      toast(`✓ Tap aprobado · RC=${r.rc} · auth ${r.auth_code}`, "success");
    } else {
      toast(`✗ Tap rechazado · RC=${r.rc} · ${r.message}`, "error");
    }
    await refreshBalance();
    await loadTxns();
  } catch (e) {
    toast("Error: " + e.message, "error");
  } finally {
    $("#btn-tap").disabled = false;
  }
}

// --- transacciones --------------------------------------------------
async function loadTxns() {
  const r = await api("GET", "/transactions");
  const tbody = $("#txn-table tbody");
  tbody.innerHTML = "";
  for (const t of r.transactions) {
    const tr = document.createElement("tr");
    const actions = [];
    if (t.state === "authorized") {
      actions.push(`<button data-cap="${t.txn_id}" class="small">capture</button>`);
      actions.push(`<button data-rev="${t.txn_id}" class="small">reverse</button>`);
    }
    tr.innerHTML = `
      <td>${t.txn_id}</td>
      <td>${t.pan_masked}</td>
      <td>${fmtMoney(t.amount_minor, t.currency)}</td>
      <td>${t.pos_entry}</td>
      <td><span class="state-pill ${t.state}">${t.state}</span></td>
      <td>${t.response_code}</td>
      <td>${t.auth_code || "—"}</td>
      <td>${actions.join(" ")}</td>
    `;
    tbody.appendChild(tr);
  }
  tbody.querySelectorAll("[data-cap]").forEach(b => {
    b.onclick = async () => {
      try { await api("POST", "/capture", { txn_id: b.dataset.cap });
            toast("Capturada", "success"); await refreshBalance(); await loadTxns(); }
      catch (e) { toast("Error: " + e.message, "error"); }
    };
  });
  tbody.querySelectorAll("[data-rev]").forEach(b => {
    b.onclick = async () => {
      try { await api("POST", "/reverse", { txn_id: b.dataset.rev });
            toast("Reversada", "success"); await refreshBalance(); await loadTxns(); }
      catch (e) { toast("Error: " + e.message, "error"); }
    };
  });
}

async function runClearing() {
  try {
    const r = await api("POST", "/clearing/run");
    toast(`Clearing batch: ${r.captured_now} capturadas, ${r.settled} liquidadas`, "success");
    await refreshBalance();
    await loadTxns();
  } catch (e) {
    toast("Error: " + e.message, "error");
  }
}

// --- bind -----------------------------------------------------------
$("#btn-issue").onclick     = issueCard;
$("#btn-refresh").onclick   = refreshBalance;
$("#btn-charge").onclick    = charge;
$("#btn-provision").onclick = provision;
$("#btn-tap").onclick       = tap;
$("#btn-clearing").onclick  = runClearing;
$("#btn-reload").onclick    = loadTxns;

checkHealth();
loadTxns();
setInterval(checkHealth, 15000);
