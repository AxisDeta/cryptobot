function getDeviceId() {
  const key = "ctb_device_id";
  let val = localStorage.getItem(key);
  if (!val) {
    val = `dev_${Math.random().toString(36).slice(2)}_${Date.now()}`;
    localStorage.setItem(key, val);
  }
  return val;
}

function getActivationKey() {
  return (localStorage.getItem("ctb_activation_key") || "").trim();
}

function setActivationKey(key) {
  localStorage.setItem("ctb_activation_key", key);
  const input = document.getElementById("activation-key");
  if (input) input.value = key;
}

function cacheGet(key, maxAgeMs) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    if (Date.now() - Number(parsed.ts || 0) > maxAgeMs) return null;
    return parsed.value;
  } catch (_err) {
    return null;
  }
}

function cacheSet(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify({ ts: Date.now(), value }));
  } catch (_err) {
    // ignore
  }
}

function cacheDel(key) {
  try { localStorage.removeItem(key); } catch (_err) { /* ignore */ }
}

function authHeaders() {
  const key = getActivationKey();
  const out = { "Content-Type": "application/json", "x-device-id": getDeviceId() };
  if (key) out["x-activation-key"] = key;
  return out;
}

function setAccountMsg(msg, ok = true) {
  const node = document.getElementById("account-msg");
  if (!node) return;
  node.textContent = msg;
  node.style.color = ok ? "#86efac" : "#fca5a5";
}

function payloadMessage(payload, fallback = "Request failed") {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (Array.isArray(payload)) return payload.map((p) => payloadMessage(p, "")).filter(Boolean).join("; ") || fallback;
  if (typeof payload === "object") {
    if (typeof payload.detail === "string") return payload.detail;
    if (typeof payload.error === "string") return payload.error;
    if (typeof payload.message === "string") return payload.message;
    if (Array.isArray(payload.detail)) {
      const msgs = payload.detail.map((d) => payloadMessage(d, "")).filter(Boolean);
      if (msgs.length) return msgs.join("; ");
    }
    try { return JSON.stringify(payload); } catch (_err) { return fallback; }
  }
  return String(payload);
}

function errorMessage(err, fallback = "Request failed") {
  if (!err) return fallback;
  if (err instanceof Error) return err.message || fallback;
  if (typeof err === "string") return err;
  return payloadMessage(err, fallback);
}

function setLicenseStatus(active, text) {
  const dot = document.getElementById("license-dot");
  const label = document.getElementById("license-text");
  if (!dot || !label) return;
  dot.style.background = active ? "#16a34a" : "#ef4444";
  label.textContent = text;
}

function setBillingPanelVisible(visible, allowClose = false) {
  const panel = document.getElementById("billing-panel");
  const manageBtn = document.getElementById("manage-subscription-btn");
  const closeBtn = document.getElementById("close-billing-btn");
  if (!panel || !manageBtn || !closeBtn) return;
  panel.style.display = visible ? "block" : "none";
  manageBtn.style.display = visible ? "none" : "inline-block";
  closeBtn.style.display = visible ? "inline-block" : "none";
}

function applyLicenseUiState(active) {
  setBillingPanelVisible(!active, false);
}

let checkoutBusy = false;
let activateBusy = false;

function setCheckoutLoading(busy) {
  const btn = document.getElementById("checkout-btn");
  const plan = document.getElementById("plan-code");
  if (!btn) return;
  if (!btn.dataset.defaultLabel) btn.dataset.defaultLabel = btn.textContent || "Checkout";
  btn.disabled = busy;
  btn.classList.toggle("btn-loading", busy);
  btn.textContent = busy ? "Initializing..." : btn.dataset.defaultLabel;
  if (plan) plan.disabled = busy;
}

function setActivateLoading(busy) {
  const btn = document.getElementById("activate-btn");
  const input = document.getElementById("activation-key");
  if (!btn) return;
  if (!btn.dataset.defaultLabel) btn.dataset.defaultLabel = btn.textContent || "Activate Key";
  btn.disabled = busy;
  btn.classList.toggle("btn-loading", busy);
  btn.textContent = busy ? "Activating..." : btn.dataset.defaultLabel;
  if (input) input.disabled = busy;
}

const EXCHANGE_SUPPORTED_PAIRS = {
  binance: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"],
  kraken: ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD", "DOT/USD"],
  coinbase: ["BTC/USD", "ETH/USD", "SOL/USD", "AVAX/USD", "LTC/USD", "LINK/USD"],
};

const FOREX_SUPPORTED_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY"];

const PLAN_PRICE_KSH = { test_ksh1: 500, monthly: 1500, quarterly: 3900, yearly: 12000 };
const RISK_PROFILES = {
  conservative: { positionFactor: 0.6, note: "Conservative: smaller position and stricter confidence filter." },
  moderate: { positionFactor: 1.0, note: "Moderate: balanced risk and opportunity." },
  aggressive: { positionFactor: 1.35, note: "Aggressive: larger position with higher drawdown risk." },
};

function selectedPlanCode() {
  const plan = document.getElementById("plan-code");
  return plan ? String(plan.value || "monthly") : "monthly";
}

function planRequiresPaystack(code) {
  return Number(PLAN_PRICE_KSH[code] || 0) > 2000;
}

function updatePaymentProviderUi() {
  // provider auto selection
}

function selectedRiskProfile() {
  const node = document.getElementById("risk-profile");
  return String((node && node.value) || "moderate").toLowerCase();
}

function updateRiskNote() {
  const note = document.getElementById("risk-note");
  if (!note) return;
  const profile = selectedRiskProfile();
  const cfg = RISK_PROFILES[profile] || RISK_PROFILES.moderate;
  note.textContent = cfg.note;
}

function watchlistKey() {
  return `ctb_watchlist_${getDeviceId()}`;
}

function getWatchlist() {
  const val = cacheGet(watchlistKey(), 365 * 24 * 3600 * 1000);
  return Array.isArray(val) ? val : [];
}

function setWatchlist(items) {
  cacheSet(watchlistKey(), items.slice(0, 12));
}

function renderWatchlist() {
  const host = document.getElementById("watchlist-items");
  if (!host) return;
  const items = getWatchlist();
  if (!items.length) {
    host.innerHTML = "<span class=\"hint\">No watchlist items yet.</span>";
    return;
  }
  host.innerHTML = items.map((item, idx) => {
    const text = `${item.market_type}:${item.exchange}:${item.symbol}`;
    return `<button type=\"button\" class=\"watch-chip\" data-idx=\"${idx}\">${text}</button>`;
  }).join("");

  host.querySelectorAll(".watch-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-idx") || -1);
      const row = items[idx];
      if (!row) return;
      const market = document.getElementById("market-type-input");
      const exchange = document.getElementById("exchange-input");
      const symbol = document.getElementById("symbol-input");
      if (market) market.value = row.market_type;
      if (exchange) exchange.value = row.exchange;
      updateSymbolUi();
      if (symbol) symbol.value = row.symbol;
      setAccountMsg(`Loaded watchlist pair: ${row.symbol}`, true);
    });
  });
}

function addCurrentToWatchlist() {
  const market = String(document.getElementById("market-type-input")?.value || "crypto");
  const exchange = String(document.getElementById("exchange-input")?.value || "binance");
  const symbol = String(document.getElementById("symbol-input")?.value || "").trim().toUpperCase();
  if (!symbol) {
    setAccountMsg("Enter a symbol before adding to watchlist.", false);
    return;
  }
  const items = getWatchlist();
  const exists = items.some((x) => x.market_type === market && x.exchange === exchange && x.symbol === symbol);
  if (!exists) items.unshift({ market_type: market, exchange, symbol });
  setWatchlist(items);
  renderWatchlist();
  setAccountMsg(`Added ${symbol} to watchlist.`, true);
}

function signalHistoryKey() {
  return `ctb_signal_history_${getDeviceId()}`;
}

function getSignalHistory() {
  const val = cacheGet(signalHistoryKey(), 365 * 24 * 3600 * 1000);
  return Array.isArray(val) ? val : [];
}

function setSignalHistory(items) {
  cacheSet(signalHistoryKey(), items.slice(0, 40));
}

function renderSignalHistory() {
  const host = document.getElementById("signal-history");
  if (!host) return;
  const items = getSignalHistory();
  if (!items.length) {
    host.textContent = "No signals yet.";
    return;
  }
  host.innerHTML = items.map((row, idx) => {
    const t = row.ts ? new Date(row.ts).toLocaleString() : "-";
    return `<div class="history-item"><strong>${row.action}</strong> ${row.symbol} (${row.timeframe}) | conf ${fmtPct(row.confidence)} | ${t}<br/><label>Outcome <select data-history-idx="${idx}" data-signal-id="${Number(row.signal_id || 0)}"><option value="pending" ${row.outcome === "pending" ? "selected" : ""}>Pending</option><option value="win" ${row.outcome === "win" ? "selected" : ""}>Win</option><option value="loss" ${row.outcome === "loss" ? "selected" : ""}>Loss</option><option value="skip" ${row.outcome === "skip" ? "selected" : ""}>Skipped</option></select></label></div>`;
  }).join("");
  host.querySelectorAll("select[data-history-idx]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      const idx = Number(sel.getAttribute("data-history-idx") || -1);
      const rows = getSignalHistory();
      if (!rows[idx]) return;
      const previous = rows[idx].outcome || "pending";
      rows[idx].outcome = String(sel.value || "pending");
      setSignalHistory(rows);
      const signalId = Number(sel.getAttribute("data-signal-id") || rows[idx].signal_id || 0);
      if (signalId > 0) {
        try {
          await fetch(`/api/signals/outcomes/${signalId}`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ outcome: rows[idx].outcome }),
          });
        } catch (_err) {
          rows[idx].outcome = previous;
          setSignalHistory(rows);
          sel.value = previous;
        }
      }
    });
  });
}

async function saveSignalHistory(result, payload) {
  let signalId = 0;
  try {
    const response = await fetch("/api/signals/outcomes", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        symbol: payload.symbol,
        timeframe: payload.timeframe,
        action: String(result.trade_action || result.signal || "WAIT"),
        confidence: Number(result.confidence || 0),
        outcome: "pending",
      }),
    });
    const data = await response.json();
    if (response.ok) signalId = Number(data.signal_id || 0);
  } catch (_err) {
    signalId = 0;
  }

  const rows = getSignalHistory();
  rows.unshift({
    signal_id: signalId,
    ts: Date.now(),
    market_type: payload.market_type,
    exchange: payload.exchange,
    symbol: payload.symbol,
    timeframe: payload.timeframe,
    action: String(result.trade_action || result.signal || "WAIT"),
    confidence: Number(result.confidence || 0),
    outcome: "pending",
  });
  setSignalHistory(rows);
  renderSignalHistory();
}

function setLoadingState(loading) {
  const res = document.getElementById("results-skeleton");
  const ch = document.getElementById("chart-skeleton");
  const metrics = document.getElementById("advanced-metrics");
  const notes = document.getElementById("advanced-notes");
  if (res) res.style.display = loading ? "block" : "none";
  if (ch) ch.style.display = loading ? "block" : "none";
  if (metrics) metrics.style.opacity = loading ? "0.45" : "1";
  if (notes) notes.style.opacity = loading ? "0.45" : "1";
}

function explainSummary(result) {
  const node = document.getElementById("explain-summary");
  if (!node) return;
  const pUp = Number(result.direction_prob_up || 0);
  const pDown = Math.max(0, 1 - pUp);
  const conf = Number(result.confidence || 0);
  const act = String(result.trade_action || "WAIT").toUpperCase();
  node.textContent = `${act}. Up chance ${Math.round(pUp * 100)}%, down chance ${Math.round(pDown * 100)}%, confidence ${Math.round(conf * 100)}%.`;
}

function formatDaysLeft(expiresAt) {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (!Number.isFinite(ms)) return null;
  return Math.max(0, Math.ceil(ms / (24 * 3600 * 1000)));
}

function updateSubscriptionBadge(items) {
  const badge = document.getElementById("subscription-badge");
  if (!badge) return;
  const active = (items || []).filter((x) => String(x.status || "").toLowerCase() === "active");
  if (!active.length) {
    badge.textContent = "No active subscription";
    return;
  }
  const first = active[0];
  const days = formatDaysLeft(first.expires_at);
  const plan = String(first.plan_code || "").toUpperCase();
  badge.textContent = days == null ? `${plan} active` : `${plan} active | ${days} day(s) left`;
}

function maybeShowOnboarding() {
  const key = "ctb_onboarding_seen";
  const card = document.getElementById("onboarding-card");
  if (!card) return;
  const seen = localStorage.getItem(key) === "1";
  card.style.display = seen ? "none" : "block";
}

function dismissOnboarding() {
  localStorage.setItem("ctb_onboarding_seen", "1");
  const card = document.getElementById("onboarding-card");
  if (card) card.style.display = "none";
}

function updateSymbolUi() {
  const marketNode = document.getElementById("market-type-input");
  const ex = document.getElementById("exchange-input");
  const symbol = document.getElementById("symbol-input");
  const hint = document.getElementById("symbol-hint");
  const list = document.getElementById("symbol-suggestions");
  if (!symbol || !hint || !list) return;

  const marketType = String((marketNode && marketNode.value) || "crypto").toLowerCase();
  const exchangeLabel = ex ? ex.closest("label") : null;
  let pairs = [];

  if (marketType === "forex") {
    pairs = FOREX_SUPPORTED_PAIRS;
    if (exchangeLabel) exchangeLabel.style.display = "none";
  } else {
    const key = String((ex && ex.value) || "binance").toLowerCase();
    pairs = EXCHANGE_SUPPORTED_PAIRS[key] || EXCHANGE_SUPPORTED_PAIRS.binance;
    if (exchangeLabel) exchangeLabel.style.display = "block";
  }

  list.innerHTML = "";
  pairs.forEach((pair) => {
    const opt = document.createElement("option");
    opt.value = pair;
    list.appendChild(opt);
  });

  if (marketType === "forex") hint.textContent = `Popular FX pairs: ${pairs.slice(0, 6).join(", ")}.`;
  else if (ex) hint.textContent = `Popular on ${ex.value}: ${pairs.slice(0, 4).join(", ")}.`;

  const current = String(symbol.value || "").trim().toUpperCase();
  if (!current || !pairs.includes(current)) symbol.value = pairs[0];
}

async function checkHealth() {
  const dot = document.getElementById("health-dot");
  const text = document.getElementById("health-text");
  if (!dot || !text) return;

  const cached = cacheGet("ctb_health_cache", 10000);
  if (cached && cached.status === "ok") {
    dot.style.background = "#16a34a";
    text.textContent = "System online";
    return;
  }

  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("health request failed");
    dot.style.background = "#16a34a";
    text.textContent = "System online";
    cacheSet("ctb_health_cache", { status: "ok" });
  } catch (_err) {
    dot.style.background = "#ef4444";
    text.textContent = "System unavailable";
  }
}

async function checkLicenseStatus() {
  const cacheKey = `ctb_license_cache_${getDeviceId()}`;
  const cached = cacheGet(cacheKey, 20000);
  if (cached && typeof cached.active === "boolean") {
    setLicenseStatus(cached.active, cached.active ? "License active" : "License not active");
    applyLicenseUiState(cached.active);
    return cached.active;
  }

  try {
    const response = await fetch("/api/license/status", { headers: authHeaders() });
    const data = await response.json();
    const active = Boolean(data.active);
    setLicenseStatus(active, active ? "License active" : "License not active");
    applyLicenseUiState(active);
    cacheSet(cacheKey, { active });
    return active;
  } catch (_err) {
    setLicenseStatus(false, "License check failed");
    applyLicenseUiState(false);
    return false;
  }
}

async function loadSubscriptions(force = false) {
  const host = document.getElementById("subscription-list");
  if (!host) return;

  const cacheKey = `ctb_subscriptions_cache_${getDeviceId()}`;
  if (!force) {
    const cached = cacheGet(cacheKey, 60000);
    if (cached && Array.isArray(cached.items)) {
      updateSubscriptionBadge(cached.items);
      renderSubscriptionRows(host, cached.items);
      return;
    }
  }

  host.textContent = "Loading subscriptions...";
  try {
    const res = await fetch("/api/license/subscriptions?limit=30", { headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(payloadMessage(data, "Failed to load subscriptions"));
    const items = Array.isArray(data.items) ? data.items : [];
    const activeWithKey = items.find((s) => String(s.status || "").toLowerCase() === "active" && String(s.activation_key || "").startsWith("CTB-"));
    if (activeWithKey) {
      const activeKey = String(activeWithKey.activation_key || "").trim();
      const saved = getActivationKey();
      if (activeKey && (!saved || saved !== activeKey)) {
        setActivationKey(activeKey);
      }
    }
    cacheSet(cacheKey, { items });
    updateSubscriptionBadge(items);
    renderSubscriptionRows(host, items);
    await checkLicenseStatus();
  } catch (err) {
    host.textContent = errorMessage(err, "Unable to load subscriptions.");
    updateSubscriptionBadge([]);
  }
}

function renderSubscriptionRows(host, items) {
  if (!items.length) {
    host.textContent = "No subscriptions yet.";
    return;
  }
  const activeItems = items.filter((s) => String(s.status || "").toLowerCase() === "active");
  const renderItems = activeItems.length ? activeItems : items;

  host.innerHTML = renderItems.map((s) => {
    const plan = String(s.plan_code || "-").toUpperCase();
    const status = String(s.status || "-");
    const key = String(s.activation_key || s.activation_key_hint || "-");
    const issued = s.issued_at ? (new Date(s.issued_at).toLocaleString() || s.issued_at) : "-";
    const activated = s.activated_at ? (new Date(s.activated_at).toLocaleString() || s.activated_at) : "-";
    const expires = s.expires_at ? (new Date(s.expires_at).toLocaleString() || s.expires_at) : "-";
    return `<div class="sub-item"><strong>${plan}</strong> | ${status}<br/><span>Activation Key: <code>${key}</code></span><br/><span>Issued: ${issued}</span><br/><span>Activated: ${activated}</span><br/><span><strong>Expires:</strong> ${expires}</span></div>`;
  }).join("");
}

function fmtPct(v) { return `${(Number(v) * 100).toFixed(2)}%`; }
function setMetric(id, value) { const node = document.getElementById(id); if (node) node.textContent = value; }

function renderSignal(signal, confidence) {
  const badge = document.getElementById("signal-badge");
  const note = document.getElementById("signal-note");
  if (!badge || !note) return;
  const s = String(signal || "Wait").toLowerCase();
  if (s === "bullish") {
    badge.className = "badge bullish";
    badge.textContent = "BULLISH";
    note.textContent = `Potential upside setup. Confidence ${fmtPct(confidence)}.`;
  } else if (s === "bearish") {
    badge.className = "badge bearish";
    badge.textContent = "BEARISH";
    note.textContent = `Downside pressure detected. Confidence ${fmtPct(confidence)}.`;
  } else {
    badge.className = "badge neutral";
    badge.textContent = "WAIT";
    note.textContent = `No high-quality edge yet. Confidence ${fmtPct(confidence)}.`;
  }
}

function renderSpotlight(result) {
  const root = document.getElementById("signal-spotlight");
  const action = document.getElementById("spotlight-action");
  const reason = document.getElementById("spotlight-reason");
  if (!root || !action || !reason) return;

  const tradeAction = String(result.trade_action || "WAIT").toUpperCase();
  action.textContent = tradeAction;
  reason.textContent = result.trade_guidance || "No guidance available yet.";

  root.classList.remove("buy", "sell", "wait");
  if (tradeAction.includes("BUY")) root.classList.add("buy");
  else if (tradeAction.includes("SELL")) root.classList.add("sell");
  else root.classList.add("wait");
}

function renderInsights(result) {
  const posts = document.getElementById("posts-insight");
  const ai = document.getElementById("ai-insight");
  const quality = document.getElementById("quality-insight");
  if (posts) posts.textContent = `Posts analyzed: ${result.num_posts ?? 0}`;
  if (ai) ai.textContent = `AI Analyst: ${result.ai_explanation_status === "ok" ? "ready" : "fallback"}`;
  if (quality) quality.textContent = `Reliability: ${fmtPct(result.confidence ?? 0)}`;
}

function getBeginnerModeEnabled() { return localStorage.getItem("ctb_beginner_mode") === "1"; }
function setBeginnerModeEnabled(enabled) { localStorage.setItem("ctb_beginner_mode", enabled ? "1" : "0"); }

function applyResultMode() {
  const beginner = getBeginnerModeEnabled();
  const beginnerCard = document.getElementById("beginner-card");
  const advancedMetrics = document.getElementById("advanced-metrics");
  const advancedNotes = document.getElementById("advanced-notes");
  const advancedInsights = document.getElementById("advanced-insights");
  const tradeGuide = document.getElementById("trade-guidance");
  const aiGuide = document.getElementById("ai-explanation");
  const toggle = document.getElementById("beginner-mode");

  if (toggle) toggle.checked = beginner;
  if (beginnerCard) beginnerCard.style.display = beginner ? "block" : "none";
  if (advancedMetrics) advancedMetrics.style.display = beginner ? "none" : "grid";
  if (advancedNotes) advancedNotes.style.display = beginner ? "none" : "grid";
  if (advancedInsights) advancedInsights.style.display = beginner ? "none" : "flex";
  if (tradeGuide) tradeGuide.style.display = beginner ? "none" : "block";
  if (aiGuide) aiGuide.style.display = beginner ? "none" : "block";
}

function renderBeginnerCard(result) {
  const actionNode = document.getElementById("beginner-action");
  const strengthNode = document.getElementById("beginner-strength");
  const riskNode = document.getElementById("beginner-risk");
  const whyNode = document.getElementById("beginner-why");
  const nextNode = document.getElementById("beginner-next");
  if (!actionNode || !strengthNode || !riskNode || !whyNode || !nextNode) return;

  const pUp = Number(result.direction_prob_up ?? 0);
  const conf = Number(result.confidence ?? 0);
  const vol = Number(result.expected_volatility ?? 0);
  const tradeAction = String(result.trade_action || "WAIT").toUpperCase();

  let action = "Wait";
  if (tradeAction.includes("BUY")) action = "Buy bias";
  else if (tradeAction.includes("SELL") || tradeAction.includes("BEAR")) action = "Sell bias";

  let strength = "Weak";
  if (conf >= 0.7) strength = "Strong";
  else if (conf >= 0.55) strength = "Medium";

  let risk = "Medium";
  if (vol >= 0.01 || conf < 0.5) risk = "High";
  else if (vol < 0.004 && conf >= 0.6) risk = "Low";

  const why = result.ai_explanation || `${Math.round(pUp * 100)}% chance price goes up, confidence ${Math.round(conf * 100)}%.`;
  const next = strength === "Strong" ? "If this matches your strategy, consider a small risk-managed trade." : "As a beginner, wait for stronger signals before entering.";

  actionNode.textContent = action;
  strengthNode.textContent = strength;
  riskNode.textContent = risk;
  whyNode.textContent = why;
  nextNode.textContent = next;
}

function toMs(t) {
  const n = Number(t || 0);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n < 1e12 ? n * 1000 : n;
}

function getChartToggles() {
  const ema = document.getElementById("toggle-ema");
  const signals = document.getElementById("toggle-signals");
  const prob = document.getElementById("toggle-prob");
  const windowMode = document.getElementById("chart-window");
  return {
    ema: !!(ema && ema.checked),
    signals: !!(signals && signals.checked),
    prob: !!(prob && prob.checked),
    context: !!(windowMode && windowMode.value === "context"),
  };
}

function applyChartDefaults() {
  const isMobile = window.matchMedia("(max-width: 768px)").matches;
  const ema = document.getElementById("toggle-ema");
  const signals = document.getElementById("toggle-signals");
  const prob = document.getElementById("toggle-prob");
  const windowMode = document.getElementById("chart-window");
  if (ema && !ema.dataset.init) { ema.checked = !isMobile; ema.dataset.init = "1"; }
  if (signals && !signals.dataset.init) { signals.checked = false; signals.dataset.init = "1"; }
  if (prob && !prob.dataset.init) { prob.checked = true; prob.dataset.init = "1"; }
  if (windowMode && !windowMode.dataset.init) { windowMode.value = "prediction"; windowMode.dataset.init = "1"; }
}

function buildEmaSeries(candles, period) {
  if (!Array.isArray(candles) || !candles.length) return [];
  const alpha = 2 / (period + 1);
  const out = [];
  let prev = Number(candles[0].close || 0);
  for (let i = 0; i < candles.length; i += 1) {
    const c = Number(candles[i].close || 0);
    prev = i === 0 ? c : (alpha * c) + ((1 - alpha) * prev);
    out.push({ time: candles[i].time, value: prev });
  }
  return out;
}

function drawPriceModelChart(chartData) {
  const priceContainer = document.getElementById("chart-price");
  const probContainer = document.getElementById("chart-prob");
  if (!priceContainer || !probContainer) return;
  const toggles = getChartToggles();

  const probs = Array.isArray(chartData.direction_probs) ? chartData.direction_probs : [];
  const predCandles = Array.isArray(chartData.candles) ? chartData.candles : [];
  const contextCandles = Array.isArray(chartData.context_candles) ? chartData.context_candles : [];
  const candles = toggles.context ? [...contextCandles, ...predCandles] : predCandles;

  if (!candles.length) {
    priceContainer.textContent = "No candle data available.";
    probContainer.style.display = "none";
    return;
  }

  const emaFast = toggles.context ? buildEmaSeries(candles, 12) : (Array.isArray(chartData.ema_fast) ? chartData.ema_fast : []);
  const emaSlow = toggles.context ? buildEmaSeries(candles, 26) : (Array.isArray(chartData.ema_slow) ? chartData.ema_slow : []);
  const markers = Array.isArray(chartData.trade_markers) ? chartData.trade_markers : [];

  if (!window.Plotly) {
    priceContainer.textContent = "Plotly not loaded.";
    probContainer.style.display = "none";
    return;
  }

  const x = candles.map((c) => new Date(toMs(c.time)));
  const open = candles.map((c) => Number(c.open));
  const high = candles.map((c) => Number(c.high));
  const low = candles.map((c) => Number(c.low));
  const close = candles.map((c) => Number(c.close));

  const priceTraces = [{ type: "candlestick", x, open, high, low, close, name: "Price", increasing: { line: { color: "#22c55e" } }, decreasing: { line: { color: "#ef4444" } } }];
  if (toggles.ema && emaFast.length) priceTraces.push({ type: "scatter", mode: "lines", name: "EMA 12", x: emaFast.map((p) => new Date(toMs(p.time))), y: emaFast.map((p) => Number(p.value)), line: { color: "#38bdf8", width: 1.4 } });
  if (toggles.ema && emaSlow.length) priceTraces.push({ type: "scatter", mode: "lines", name: "EMA 26", x: emaSlow.map((p) => new Date(toMs(p.time))), y: emaSlow.map((p) => Number(p.value)), line: { color: "#a78bfa", width: 1.4 } });
  if (toggles.signals && markers.length) {
    const capped = markers.slice(-12);
    const buys = capped.filter((m) => String(m.side).toLowerCase() === "buy");
    const sells = capped.filter((m) => String(m.side).toLowerCase() === "sell");
    if (buys.length) priceTraces.push({ type: "scatter", mode: "markers", name: "Buy", x: buys.map((m) => new Date(toMs(m.time))), y: buys.map((m) => Number(m.price)), marker: { color: "#22c55e", size: 8, symbol: "triangle-up" } });
    if (sells.length) priceTraces.push({ type: "scatter", mode: "markers", name: "Sell", x: sells.map((m) => new Date(toMs(m.time))), y: sells.map((m) => Number(m.price)), marker: { color: "#ef4444", size: 8, symbol: "triangle-down" } });
  }

  Plotly.react(priceContainer, priceTraces, {
    paper_bgcolor: "#0a1220", plot_bgcolor: "#0a1220", font: { color: "#dbeafe", size: 11 }, margin: { l: 45, r: 24, t: 8, b: 30 }, showlegend: true, legend: { orientation: "h", y: 1.08, x: 0 },
    xaxis: { rangeslider: { visible: false }, gridcolor: "rgba(255,255,255,0.08)" }, yaxis: { title: "Price", gridcolor: "rgba(255,255,255,0.08)" },
  }, { responsive: true, displayModeBar: false });

  if (!toggles.prob || !probs.length) {
    probContainer.style.display = "none";
    return;
  }
  probContainer.style.display = "block";
  Plotly.react(probContainer, [{ type: "scatter", mode: "lines", name: "P(up)", x: probs.map((p) => new Date(toMs(p.time))), y: probs.map((p) => Number(p.value)), line: { color: "#f59e0b", width: 2 } }], {
    paper_bgcolor: "#0a1220", plot_bgcolor: "#0a1220", font: { color: "#dbeafe", size: 11 }, margin: { l: 45, r: 24, t: 8, b: 30 }, showlegend: false,
    xaxis: { gridcolor: "rgba(255,255,255,0.08)" }, yaxis: { title: "P(up)", range: [0, 1], tickformat: ".0%", gridcolor: "rgba(255,255,255,0.08)" },
  }, { responsive: true, displayModeBar: false });
}

function renderMetricNotes(result) {
  const notes = result.metric_notes || {};
  const guide = document.getElementById("trade-guidance");
  const ai = document.getElementById("ai-explanation");
  const d = document.getElementById("direction_prob_up_note");
  const c = document.getElementById("confidence_note");
  const v = document.getElementById("expected_volatility_note");
  const p = document.getElementById("recommended_position_note");
  if (d) d.textContent = `Up Probability: ${notes.direction_prob_up || "--"}`;
  if (c) c.textContent = `Confidence: ${notes.confidence || "--"}`;
  if (v) v.textContent = `Expected Volatility: ${notes.expected_volatility || "--"}`;
  if (p) p.textContent = `Position Size: ${notes.recommended_position || "--"}`;
  if (guide) guide.textContent = `${result.trade_action || "WAIT"}: ${result.trade_guidance || "No guidance available yet."}`;
  if (ai) ai.textContent = result.ai_explanation || "AI explanation unavailable; using rules-based guidance.";
}

async function renderResult(result, payload = null) {
  const profile = selectedRiskProfile();
  const cfg = RISK_PROFILES[profile] || RISK_PROFILES.moderate;
  const basePos = Number(result.recommended_position ?? 0);
  const adjPos = Math.max(0, basePos * cfg.positionFactor);

  setMetric("direction_prob_up", fmtPct(result.direction_prob_up ?? 0));
  setMetric("expected_volatility", fmtPct(result.expected_volatility ?? 0));
  setMetric("confidence", fmtPct(result.confidence ?? 0));
  setMetric("recommended_position", adjPos.toFixed(2));

  renderSignal(result.signal, result.confidence ?? 0);
  renderSpotlight(result);
  renderInsights(result);
  renderMetricNotes(result);
  renderBeginnerCard(result);
  explainSummary(result);
  applyResultMode();

  const chartData = result.chart || {};
  window.__lastChartData = chartData;
  drawPriceModelChart(chartData);

  if (payload) await saveSignalHistory(result, payload);
}

function readPayload(form) {
  const fd = new FormData(form);
  const market_type = String(fd.get("market_type") || "crypto").toLowerCase();
  return {
    market_type,
    exchange: String(fd.get("exchange") || "binance"),
    symbol: String(fd.get("symbol") || (market_type === "forex" ? "EUR/USD" : "BTC/USDT")),
    timeframe: String(fd.get("timeframe") || "1h"),
    risk_profile: String(fd.get("risk_profile") || selectedRiskProfile()),
  };
}

async function runPrediction(event) {
  event.preventDefault();
  const button = document.getElementById("run-btn");
  if (!button) return;
  const payload = readPayload(event.currentTarget);
  const requestPayload = { market_type: payload.market_type, exchange: payload.exchange, symbol: payload.symbol, timeframe: payload.timeframe };
  button.disabled = true;
  button.textContent = "Analyzing...";
  setLoadingState(true);
  try {
    const response = await fetch("/api/predict", { method: "POST", headers: authHeaders(), body: JSON.stringify(requestPayload) });
    const data = await response.json();
    if (!response.ok) throw new Error(payloadMessage(data, "Prediction failed"));
    await renderResult(data, payload);
  } catch (err) {
    renderSignal("wait", 0);
    const note = document.getElementById("signal-note");
    if (note) note.textContent = String(err);
  } finally {
    button.disabled = false;
    button.textContent = "Generate Signal";
    setLoadingState(false);
  }
}

async function startCheckout(provider) {
  const planNode = document.getElementById("plan-code");
  const plan_code = planNode ? planNode.value : "monthly";
  const response = await fetch("/api/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, plan_code }),
  });
  let data = {};
  try { data = await response.json(); } catch (_err) { data = {}; }
  if (!response.ok) throw new Error(payloadMessage(data, "Checkout failed"));
  const url = data.redirect_url || data.authorization_url;
  if (!url) throw new Error("Payment link missing");
  window.location.href = url;
}

async function activateKey() {
  const input = document.getElementById("activation-key");
  const activation_key = input ? input.value.replace(/\s+/g, "").toUpperCase() : "";
  const device_id = getDeviceId();
  const response = await fetch("/api/license/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ activation_key, device_id }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(payloadMessage(data, "Activation failed"));
  setActivationKey(activation_key);
  const expiresRaw = data.expires_at || "";
  const expiresText = expiresRaw ? (new Date(expiresRaw).toLocaleString() || expiresRaw) : "-";
  setLicenseStatus(true, `License active | Expires: ${expiresText}`);
  setAccountMsg("Activation successful.", true);
  applyLicenseUiState(true);
  cacheDel(`ctb_subscriptions_cache_${getDeviceId()}`);
  await loadSubscriptions(true);
}

function logout() {
  localStorage.removeItem("ctb_activation_key");
  window.location.href = "/logout";
}

window.addEventListener("DOMContentLoaded", async () => {
  const predictForm = document.getElementById("predict-form");
  const exchangeInput = document.getElementById("exchange-input");
  const marketTypeInput = document.getElementById("market-type-input");
  const checkoutBtn = document.getElementById("checkout-btn");
  const planCodeNode = document.getElementById("plan-code");
  const activateBtn = document.getElementById("activate-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const adminBtn = document.getElementById("admin-link-btn");
  const manageBtn = document.getElementById("manage-subscription-btn");
  const closeBillingBtn = document.getElementById("close-billing-btn");
  const toggleEma = document.getElementById("toggle-ema");
  const toggleSignals = document.getElementById("toggle-signals");
  const toggleProb = document.getElementById("toggle-prob");
  const chartWindow = document.getElementById("chart-window");
  const beginnerMode = document.getElementById("beginner-mode");
  const watchlistAddBtn = document.getElementById("watchlist-add-btn");
  const riskProfile = document.getElementById("risk-profile");
  const onboardingDismissBtn = document.getElementById("onboarding-dismiss-btn");applyChartDefaults();
  applyResultMode();
  updatePaymentProviderUi();
  updateSymbolUi();
  updateRiskNote();
  renderWatchlist();
  renderSignalHistory();
  maybeShowOnboarding();

  if (predictForm) predictForm.addEventListener("submit", runPrediction);

  if (checkoutBtn) {
    checkoutBtn.addEventListener("click", async () => {
      if (checkoutBusy) return;
      checkoutBusy = true;
      setCheckoutLoading(true);
      const code = selectedPlanCode();
      const provider = planRequiresPaystack(code) ? "paystack" : "pesapal";
      try {
        await startCheckout(provider);
      } catch (err) {
        setAccountMsg(errorMessage(err, "Checkout failed"), false);
        checkoutBusy = false;
        setCheckoutLoading(false);
      }
    });
  }

  if (activateBtn) {
    activateBtn.addEventListener("click", async () => {
      if (activateBusy) return;
      activateBusy = true;
      setActivateLoading(true);
      setAccountMsg("Activating your key...", true);
      try {
        await activateKey();
      } catch (err) {
        setAccountMsg(errorMessage(err, "Activation failed"), false);
      } finally {
        activateBusy = false;
        setActivateLoading(false);
      }
    });
  }

  if (manageBtn) manageBtn.addEventListener("click", () => setBillingPanelVisible(true, true));if (closeBillingBtn) closeBillingBtn.addEventListener("click", () => setBillingPanelVisible(false, false));
  if (watchlistAddBtn) watchlistAddBtn.addEventListener("click", addCurrentToWatchlist);
  if (riskProfile) riskProfile.addEventListener("change", updateRiskNote);
  if (onboardingDismissBtn) onboardingDismissBtn.addEventListener("click", dismissOnboarding);

  [toggleEma, toggleSignals, toggleProb, chartWindow].forEach((node) => {
    if (!node) return;
    node.addEventListener("change", () => {
      if (window.__lastChartData) drawPriceModelChart(window.__lastChartData);
    });
  });

  if (exchangeInput) exchangeInput.addEventListener("change", updateSymbolUi);
  if (marketTypeInput) marketTypeInput.addEventListener("change", updateSymbolUi);
  if (planCodeNode) planCodeNode.addEventListener("change", updatePaymentProviderUi);

  if (beginnerMode) {
    beginnerMode.addEventListener("change", () => {
      setBeginnerModeEnabled(Boolean(beginnerMode.checked));
      applyResultMode();
    });
  }

  if (logoutBtn) logoutBtn.addEventListener("click", logout);
  if (adminBtn) adminBtn.addEventListener("click", () => { window.location.href = "/admin"; });

  const saved = getActivationKey();
  const activationInput = document.getElementById("activation-key");
  if (saved && activationInput) activationInput.value = saved;

  window.addEventListener("resize", () => {
    if (window.__lastChartData) drawPriceModelChart(window.__lastChartData);
  });

  await checkHealth();
  await checkLicenseStatus();
  await loadSubscriptions();
});






















