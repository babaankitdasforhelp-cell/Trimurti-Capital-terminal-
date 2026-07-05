async function api(url, method = "GET", body = null) {
    const options = {
        method: method,
        headers: { "Content-Type": "application/json" }
    };

    if (body !== null) {
        options.body = JSON.stringify(body);
    }

    const res = await fetch(url, options);
    let data = null;
    try {
        data = await res.json();
    } catch (err) {
        data = { ok: false, message: "Invalid server response", status: res.status };
    }
    return data;
}

function el(id) {
    return document.getElementById(id);
}

function getInputValue(id, fallback = "") {
    const node = el(id);
    if (!node) return fallback;
    return node.value;
}

function setInputValue(id, value) {
    const node = el(id);
    if (!node) return;
    node.value = value ?? "";
}

function setText(id, value) {
    const node = el(id);
    if (!node) return;
    node.innerText = value ?? "";
}

function normalizeStrikeText(strike, optionType) {
    const match = String(strike || "").match(/\d+/);
    if (!match) return String(strike || "");
    return `${match[0]} ${optionType}`;
}

function currentSymbol() {
    return getInputValue("symbol", "NIFTY").trim().toUpperCase();
}

function currentExpiry() {
    return getInputValue("expiry", "").trim();
}

let lastState = null;
let lastCandles = [];
let chartCtx = null;

// =========================
// DASHBOARD STATE
// =========================
async function saveStrike() {
    const data = {
        strategy: getInputValue("strategy"),
        symbol: currentSymbol(),
        expiry: currentExpiry(),
        call_strike: normalizeStrikeText(getInputValue("callStrike"), "CE"),
        call_exchange_id: getInputValue("callExchangeId"),
        put_strike: normalizeStrikeText(getInputValue("putStrike"), "PE"),
        put_exchange_id: getInputValue("putExchangeId"),
        qty: getInputValue("qty"),
        old_webhook_url: getInputValue("oldWebhookUrl")
    };

    const res = await api("/api/save-strike", "POST", data);
    console.log("SAVE STRIKE RESULT:", res);
    alert(res.message || "Save completed");
    await loadState(true);
}

async function activateStrategy() {
    const res = await api("/api/activate", "POST", {});
    alert(res.message || "Strategy Activated");
    await loadState(false);
}

async function deactivateStrategy() {
    const res = await api("/api/deactivate", "POST", {});
    alert(res.message || "Strategy Deactivated");
    await loadState(false);
}

async function manualOrder(action) {
    const res = await api("/api/manual-order", "POST", { action: action });
    alert(res.message || `${action} Order Added`);
    await loadState(false);
}

async function squareOff() {
    const res = await api("/api/squareoff", "POST", {});
    alert(res.message || "Square off requested");
    await loadState(false);
}

async function addContractFromInputs() {
    const data = {
        symbol: currentSymbol(),
        expiry: getInputValue("contractExpiry", currentExpiry()),
        strike: getInputValue("contractStrike"),
        option_type: getInputValue("contractOptionType"),
        exchange_instrument_id: getInputValue("contractExchangeId")
    };
    const res = await api("/api/add-contract", "POST", data);
    alert(res.message || "Contract saved");
    await loadState(true);
}

async function deleteContract(index) {
    if (!confirm("Delete this contract from dashboard list?")) return;
    const res = await api("/api/delete-contract", "POST", { index });
    alert(res.message || "Contract deleted");
    await loadState(true);
}

function findContract(optionType, strikeText) {
    if (!lastState || !Array.isArray(lastState.contracts)) return null;
    const strikeNo = String(strikeText || "").match(/\d+/)?.[0] || "";
    const expiry = currentExpiry();
    const symbol = currentSymbol();
    return lastState.contracts.find(c =>
        String(c.symbol || "").toUpperCase() === symbol &&
        String(c.expiry || "") === expiry &&
        String(c.option_type || "").toUpperCase() === optionType &&
        String(c.strike || "") === strikeNo
    ) || null;
}

function autoFillContractId(optionType) {
    const strikeId = optionType === "CE" ? "callStrike" : "putStrike";
    const exchangeId = optionType === "CE" ? "callExchangeId" : "putExchangeId";
    const found = findContract(optionType, getInputValue(strikeId));
    if (found) {
        setInputValue(strikeId, found.strike_text || `${found.strike} ${optionType}`);
        setInputValue(exchangeId, found.exchange_instrument_id || "");
    }
}

function populateContractLists(state) {
    const callList = el("callStrikeList");
    const putList = el("putStrikeList");
    if (!callList || !putList) return;

    callList.innerHTML = "";
    putList.innerHTML = "";

    const contracts = Array.isArray(state.contracts) ? state.contracts : [];
    const expiry = String(state.expiry || currentExpiry());
    const symbol = String(state.symbol || "NIFTY").toUpperCase();

    contracts.forEach(c => {
        if (String(c.symbol || "").toUpperCase() !== symbol) return;
        if (String(c.expiry || "") !== expiry) return;
        const opt = document.createElement("option");
        opt.value = c.strike_text || `${c.strike} ${c.option_type}`;
        opt.label = `${c.exchange_instrument_id || "NO-ID"}`;
        if (String(c.option_type).toUpperCase() === "CE") callList.appendChild(opt);
        if (String(c.option_type).toUpperCase() === "PE") putList.appendChild(opt);
    });
}

function renderContractTable(state) {
    const tbody = el("contractRows");
    if (!tbody) return;
    tbody.innerHTML = "";
    const contracts = Array.isArray(state.contracts) ? state.contracts : [];

    contracts.forEach((c, index) => {
        tbody.innerHTML += `
            <tr>
                <td>${c.expiry ?? ""}</td>
                <td>${c.strike_text ?? ((c.strike ?? "") + " " + (c.option_type ?? ""))}</td>
                <td>${c.exchange_instrument_id ?? ""}</td>
                <td><button class="mini red" onclick="deleteContract(${index})">DEL</button></td>
            </tr>
        `;
    });
}

async function loadState(updateInputs = true) {
    const state = await api("/api/state");
    if (!state || (state.ok === false && state.message)) {
        console.error("STATE LOAD ERROR:", state);
        return;
    }

    lastState = state;

    if (updateInputs) {
        setInputValue("symbol", state.symbol);
        setInputValue("strategy", state.strategy);
        setInputValue("expiry", state.expiry);
        setInputValue("callStrike", state.call_strike);
        setInputValue("callExchangeId", state.call_exchange_id);
        setInputValue("putStrike", state.put_strike);
        setInputValue("putExchangeId", state.put_exchange_id);
        setInputValue("qty", state.qty);
        setInputValue("oldWebhookUrl", state.old_webhook_url);
        setInputValue("contractExpiry", state.expiry);
    }

    setText("activeStatus", state.strategy_active ? "ON" : "OFF");
    setText("strategyStatus", state.strategy_active ? "ON" : "OFF");

    const statusDot = el("strategyDot");
    if (statusDot) {
        statusDot.className = state.strategy_active ? "status-dot on" : "status-dot off";
    }

    if (el("pnlValue")) {
        const pnl = Number(state.pnl || 0);
        setText("pnlValue", (pnl >= 0 ? "+ ₹" : "- ₹") + Math.abs(pnl).toLocaleString("en-IN"));
    }

    const orders = el("orders");
    if (orders) {
        orders.innerHTML = "";
        const orderList = Array.isArray(state.orders) ? state.orders : [];
        orderList.forEach(o => {
            orders.innerHTML += `
                <tr>
                    <td>${o.time ?? ""}</td>
                    <td>${o.scrip ?? ""}</td>
                    <td>${o.type ?? ""}</td>
                    <td>${o.qty ?? ""}</td>
                    <td>${o.price ?? ""}</td>
                    <td>${o.status ?? ""}</td>
                </tr>
            `;
        });
    }

    populateContractLists(state);
    renderContractTable(state);
}

async function refreshRuntimeState() {
    await loadState(false);
}

// =========================
// LOCAL WEBHOOK TEST HELPERS
// =========================
async function testWebhookBuy() {
    const res = await api("/webhook", "POST", {
        Exchange: "NSEFO",
        ExchangeInstrumentId: 99999,
        SymbolName: currentSymbol(),
        SymbolSeries: "OPTIDX",
        Expiry: Number(currentExpiry() || 0),
        OptionType: "CE",
        StrikePrice: 25000,
        OrderSide: "BUY",
        OrderType: "MARKET",
        Price: 0,
        TriggerPrice: 0,
        Qty: 130,
        DisclosedQty: 0
    });
    console.log("TEST WEBHOOK CALL:", res);
    alert(res.message || "Test CALL sent");
    await loadState(false);
}

async function testWebhookSell() {
    const res = await api("/webhook", "POST", {
        Exchange: "NSEFO",
        ExchangeInstrumentId: 99999,
        SymbolName: currentSymbol(),
        SymbolSeries: "OPTIDX",
        Expiry: Number(currentExpiry() || 0),
        OptionType: "PE",
        StrikePrice: 25000,
        OrderSide: "BUY",
        OrderType: "MARKET",
        Price: 0,
        TriggerPrice: 0,
        Qty: 130,
        DisclosedQty: 0
    });
    console.log("TEST WEBHOOK PUT:", res);
    alert(res.message || "Test PUT sent");
    await loadState(false);
}

// =========================
// LOCAL CANVAS CANDLE CHART - NO CDN NEEDED
// =========================
function initNiftyChart() {
    const canvas = el("niftyLocalChart");
    if (!canvas) {
        console.error("niftyLocalChart canvas not found");
        return;
    }
    chartCtx = canvas.getContext("2d");
    resizeChartCanvas();
    window.addEventListener("resize", () => {
        resizeChartCanvas();
        drawLocalChart(lastCandles);
    });
}

function resizeChartCanvas() {
    const canvas = el("niftyLocalChart");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(300, Math.floor(rect.width * dpr));
    canvas.height = Math.max(220, Math.floor(rect.height * dpr));
    if (chartCtx) chartCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function updateChartHeader(candles) {
    if (!candles || candles.length === 0) return;
    const last = candles[candles.length - 1];
    setText("chartLtp", Number(last.close).toFixed(2));
    setText("chartOpen", Number(last.open).toFixed(2));
    setText("chartHigh", Number(last.high).toFixed(2));
    setText("chartLow", Number(last.low).toFixed(2));
    setText("chartClose", Number(last.close).toFixed(2));
}

async function loadNiftyCandles() {
    try {
        const candles = await api("/api/candles");
        if (!Array.isArray(candles)) return;
        lastCandles = candles;
        updateChartHeader(candles);
        drawLocalChart(candles);
    } catch (err) {
        console.error("Candle load error:", err);
    }
}

function drawLocalChart(candles) {
    const canvas = el("niftyLocalChart");
    if (!canvas || !chartCtx || !Array.isArray(candles) || candles.length === 0) return;

    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    const ctx = chartCtx;

    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#050914";
    ctx.fillRect(0, 0, w, h);

    const padL = 18;
    const padR = 68;
    const padT = 52;
    const padB = 28;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    // Grid
    ctx.strokeStyle = "#152033";
    ctx.lineWidth = 1;
    ctx.font = "12px Arial";
    ctx.fillStyle = "#c9d4e3";

    for (let i = 0; i <= 6; i++) {
        const y = padT + (plotH / 6) * i;
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
    }
    for (let i = 0; i <= 8; i++) {
        const x = padL + (plotW / 8) * i;
        ctx.beginPath();
        ctx.moveTo(x, padT);
        ctx.lineTo(x, h - padB);
        ctx.stroke();
    }

    const visible = candles.slice(-90);
    const highs = visible.map(c => Number(c.high));
    const lows = visible.map(c => Number(c.low));
    let maxP = Math.max(...highs);
    let minP = Math.min(...lows);
    const buffer = Math.max(10, (maxP - minP) * 0.08);
    maxP += buffer;
    minP -= buffer;
    const range = maxP - minP || 1;

    function yOf(price) {
        return padT + ((maxP - Number(price)) / range) * plotH;
    }

    // Price labels
    ctx.fillStyle = "#c9d4e3";
    for (let i = 0; i <= 6; i++) {
        const price = maxP - (range / 6) * i;
        const y = padT + (plotH / 6) * i;
        ctx.fillText(price.toFixed(2), w - padR + 8, y + 4);
    }

    const candleGap = 2;
    const candleW = Math.max(3, Math.floor(plotW / visible.length) - candleGap);

    visible.forEach((c, i) => {
        const x = padL + i * (plotW / visible.length) + (plotW / visible.length) / 2;
        const openY = yOf(c.open);
        const closeY = yOf(c.close);
        const highY = yOf(c.high);
        const lowY = yOf(c.low);
        const up = Number(c.close) >= Number(c.open);
        ctx.strokeStyle = up ? "#20d46b" : "#f04f4f";
        ctx.fillStyle = up ? "#20d46b" : "#f04f4f";

        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        const bodyTop = Math.min(openY, closeY);
        const bodyH = Math.max(2, Math.abs(closeY - openY));
        ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
    });

    // Last price line
    const last = visible[visible.length - 1];
    const lastY = yOf(last.close);
    ctx.strokeStyle = "#f04f4f";
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(padL, lastY);
    ctx.lineTo(w - padR, lastY);
    ctx.stroke();
    ctx.setLineDash([]);

    ctx.fillStyle = "#f04f4f";
    ctx.fillRect(w - padR + 2, lastY - 10, 58, 20);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 12px Arial";
    ctx.fillText(Number(last.close).toFixed(2), w - padR + 6, lastY + 4);
}

// =========================
// START APP
// =========================
document.addEventListener("DOMContentLoaded", function () {
    loadState(true);
    initNiftyChart();
    loadNiftyCandles();
    setInterval(refreshRuntimeState, 2000);
    setInterval(loadNiftyCandles, 2000);
});

// Make functions available for HTML onclick buttons
window.saveStrike = saveStrike;
window.activateStrategy = activateStrategy;
window.deactivateStrategy = deactivateStrategy;
window.manualOrder = manualOrder;
window.squareOff = squareOff;
window.testWebhookBuy = testWebhookBuy;
window.testWebhookSell = testWebhookSell;
window.addContractFromInputs = addContractFromInputs;
window.deleteContract = deleteContract;
window.autoFillContractId = autoFillContractId;
