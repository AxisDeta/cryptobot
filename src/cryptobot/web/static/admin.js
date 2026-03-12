function el(tag, text) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  return n;
}

function fmtDate(v) {
  if (!v) return "-";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString();
}

function yn(v) {
  return Number(v) ? "Yes" : "No";
}

function tableFrom(items, columns) {
  const wrap = el("div");
  if (!items || !items.length) {
    wrap.textContent = "No data";
    return wrap;
  }

  const table = el("table");
  table.style.width = "100%";
  table.style.borderCollapse = "collapse";

  const thead = el("thead");
  const hrow = el("tr");
  columns.forEach((c) => {
    const th = el("th", c.label);
    th.style.textAlign = "left";
    th.style.padding = "8px";
    th.style.borderBottom = "1px solid rgba(255,255,255,0.2)";
    hrow.appendChild(th);
  });
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = el("tbody");
  items.forEach((item) => {
    const row = el("tr");
    columns.forEach((c) => {
      const raw = typeof c.render === "function" ? c.render(item) : item[c.key];
      const td = el("td", String(raw ?? ""));
      td.style.padding = "8px";
      td.style.borderBottom = "1px solid rgba(255,255,255,0.08)";
      row.appendChild(td);
    });
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed ${url}`);
  return await res.json();
}

async function safeGet(url, fallback) {
  try {
    return await getJson(url);
  } catch (_err) {
    return fallback;
  }
}

async function postJson(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  let data = {};
  try { data = await res.json(); } catch (_err) { data = {}; }
  if (!res.ok) throw new Error(data.detail || `Failed ${url}`);
  return data;
}

function renderSignalAnalytics(data) {
  const host = document.getElementById("signal-analytics-chart");
  const summary = document.getElementById("signal-analytics-summary");
  if (!host || !summary) return;

  const counts = data.counts || {};
  const avg = data.avg_per_user || {};
  const labels = ["Wins", "Losses", "Skipped", "Pending"];
  const values = [Number(counts.win || 0), Number(counts.loss || 0), Number(counts.skip || 0), Number(counts.pending || 0)];

  summary.textContent = `Signals: ${Number(data.total || 0)} | Users tracked: ${Number(data.users_with_signals || 0)} | Avg per user → W ${Number(avg.win || 0).toFixed(2)}, L ${Number(avg.loss || 0).toFixed(2)}, S ${Number(avg.skip || 0).toFixed(2)}, P ${Number(avg.pending || 0).toFixed(2)}`;

  if (typeof Plotly === "undefined") {
    host.textContent = "Chart library unavailable.";
    return;
  }

  Plotly.react(host, [{ type: "bar", x: labels, y: values, marker: { color: ["#22c55e", "#ef4444", "#f59e0b", "#60a5fa"] } }], {
    paper_bgcolor: "#0a1220",
    plot_bgcolor: "#0a1220",
    margin: { l: 40, r: 16, t: 8, b: 35 },
    font: { color: "#dbeafe", size: 11 },
    yaxis: { title: "Count", gridcolor: "rgba(255,255,255,0.08)" },
    xaxis: { gridcolor: "rgba(255,255,255,0.05)" },
  }, { responsive: true, displayModeBar: false });
}

function renderOverview(data) {
  const container = document.getElementById("overview-cards");
  if (!container) return;
  container.innerHTML = "";
  const items = [
    ["Users", data.users],
    ["Active Users", data.active_users],
    ["Active Licenses", data.active_licenses],
    ["Completed Payments", data.completed_payments],
    ["Prediction Runs", data.prediction_runs],
  ];
  items.forEach(([label, value]) => {
    const card = el("article");
    card.className = "metric";
    card.appendChild(el("h3", label));
    card.appendChild(el("p", String(value ?? 0)));
    container.appendChild(card);
  });
}

function renderUsers(items) {
  const host = document.getElementById("users-table");
  if (!host) return;
  host.innerHTML = "";

  host.appendChild(
    tableFrom(items, [
      { key: "id", label: "User ID" },
      { key: "display_name", label: "Name" },
      { key: "email", label: "Contact (Email)" },
      { label: "Verified", render: (r) => yn(r.is_email_verified) },
      { label: "Admin", render: (r) => yn(r.is_admin) },
      { label: "Active", render: (r) => yn(r.is_active) },
      { key: "latest_plan_code", label: "Latest Plan" },
      { key: "latest_license_status", label: "Latest License Status" },
      { key: "active_license_count", label: "Active Subs" },
      { key: "completed_payments_count", label: "Completed Payments" },
      { label: "Latest Subscription Date", render: (r) => fmtDate(r.latest_issued_at) },
      { label: "Latest Activation Date", render: (r) => fmtDate(r.latest_activated_at) },
      { label: "Latest Expiry Date", render: (r) => fmtDate(r.latest_expires_at) },
      { label: "Account Created", render: (r) => fmtDate(r.created_at) },
    ])
  );

  const actions = el("div");
  actions.className = "row-actions";
  const idInput = el("input");
  idInput.placeholder = "User ID";
  const btnSetAdmin = el("button", "Set Admin");
  btnSetAdmin.onclick = async () => {
    await postJson(`/api/admin/users/${idInput.value}`, { is_admin: true });
    await refreshAll();
  };
  const btnDisable = el("button", "Disable User");
  btnDisable.onclick = async () => {
    await postJson(`/api/admin/users/${idInput.value}`, { is_active: false });
    await refreshAll();
  };
  const btnEnable = el("button", "Enable User");
  btnEnable.onclick = async () => {
    await postJson(`/api/admin/users/${idInput.value}`, { is_active: true });
    await refreshAll();
  };

  actions.append(idInput, btnSetAdmin, btnDisable, btnEnable);
  host.appendChild(actions);
}

function renderLicenses(items) {
  const host = document.getElementById("licenses-table");
  if (!host) return;
  host.innerHTML = "";

  host.appendChild(
    tableFrom(items, [
      { key: "id", label: "License ID" },
      { key: "user_id", label: "User ID" },
      { key: "email", label: "Email" },
      { key: "plan_code", label: "Plan" },
      { key: "status", label: "Status" },
      { key: "activation_key_hint", label: "Key Hint" },
      { key: "bound_device_id", label: "Device" },
      { label: "Issued", render: (r) => fmtDate(r.issued_at) },
      { label: "Activated", render: (r) => fmtDate(r.activated_at) },
      { label: "Expires", render: (r) => fmtDate(r.expires_at) },
    ])
  );

  const actions = el("div");
  actions.className = "row-actions";
  const idInput = el("input");
  idInput.placeholder = "License ID";
  const revoke = el("button", "Revoke");
  revoke.onclick = async () => {
    await postJson(`/api/admin/licenses/${idInput.value}`, { action: "revoke" });
    await refreshAll();
  };
  const clearDevice = el("button", "Clear Device");
  clearDevice.onclick = async () => {
    await postJson(`/api/admin/licenses/${idInput.value}`, { action: "clear_device" });
    await refreshAll();
  };

  actions.append(idInput, revoke, clearDevice);
  host.appendChild(actions);
}

function renderPayments(items) {
  const host = document.getElementById("payments-table");
  if (!host) return;
  host.innerHTML = "";

  host.appendChild(
    tableFrom(items, [
      { key: "id", label: "Payment ID" },
      { key: "user_id", label: "User ID" },
      { key: "email", label: "Email" },
      { key: "provider", label: "Provider" },
      { key: "plan_code", label: "Plan" },
      { key: "currency", label: "Currency" },
      { key: "amount_cents", label: "Amount (cents)" },
      { key: "status", label: "Status" },
      { key: "reference", label: "Reference" },
      { label: "Created", render: (r) => fmtDate(r.created_at) },
      { label: "Updated", render: (r) => fmtDate(r.updated_at) },
    ])
  );
}


function setSectionError(sectionId, msg) {
  const host = document.getElementById(sectionId);
  if (!host) return;
  host.innerHTML = "";
  const p = el("p", `Load error: ${msg}`);
  p.style.color = "#fca5a5";
  host.appendChild(p);
}
async function refreshAll() {
  const [overview, users, licenses, payments, signalAnalytics] = await Promise.all([
    safeGet("/api/admin/overview", { users: 0, active_users: 0, active_licenses: 0, completed_payments: 0, prediction_runs: 0 }),
    safeGet("/api/admin/users?limit=300", { items: [] }),
    safeGet("/api/admin/licenses?limit=500", { items: [] }),
    safeGet("/api/admin/payments?limit=500", { items: [] }),
    safeGet("/api/admin/signals/analytics", { total: 0, users_with_signals: 0, counts: {}, avg_per_user: {} }),
  ]);

  renderOverview(overview || {});
  renderUsers((users && users.items) || []);
  renderLicenses((licenses && licenses.items) || []);
  renderPayments((payments && payments.items) || []);
  renderSignalAnalytics(signalAnalytics || {});
}

window.addEventListener("DOMContentLoaded", async () => {
  document.getElementById("back-app-btn").onclick = () => (window.location.href = "/app");
  document.getElementById("logout-btn").onclick = () => (window.location.href = "/logout");
  document.getElementById("refresh-btn").onclick = refreshAll;

  try {
    await refreshAll();
  } catch (err) {
    document.body.append(el("p", String(err)));
  }
});
