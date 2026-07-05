from flask import Flask, render_template, jsonify, request
import json
import os
import random
import re
import time

try:
    import requests
except ImportError:
    requests = None


app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "active_state.json")

# Existing webhook fallback. Better: save old_webhook_url from dashboard input.
DEFAULT_OLD_WEBHOOK_URL = ""
FORWARD_TO_OLD_WEBHOOK = True


DEFAULT_STATE = {
    "brand_name": "Trimurti Capital",
    "symbol": "NIFTY",
    "strategy": "VP PREMIUM 5m TP SNIPER2 VOTE NO SECURITY",
    "expiry": "20260726",
    "call_strike": "24500 CE",
    "call_exchange_id": "",
    "put_strike": "24400 PE",
    "put_exchange_id": "",
    "qty": 65,
    "old_webhook_url": "",
    "strategy_active": False,
    "pnl": 5450,
    "orders": [],
    "open_positions": {},
    "contracts": []
}


# =========================
# STATE SAVE / LOAD
# =========================
def load_state():
    state = DEFAULT_STATE.copy()

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                state.update(saved)
        except Exception as e:
            print("STATE LOAD ERROR:", e)

    if not isinstance(state.get("orders"), list):
        state["orders"] = []
    if not isinstance(state.get("open_positions"), dict):
        state["open_positions"] = {}
    if not isinstance(state.get("contracts"), list):
        state["contracts"] = []

    ensure_contract_from_active(state)
    return state


def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(STATE, f, indent=4)
    except Exception as e:
        print("STATE SAVE ERROR:", e)


# =========================
# CONTRACT HELPERS
# =========================
def clean_text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def to_int_if_possible(value, default=""):
    try:
        value_str = clean_text(value)
        if value_str == "":
            return default
        return int(value_str)
    except Exception:
        return value


def extract_strike_number(strike_text):
    match = re.search(r"\d+", clean_text(strike_text))
    if match:
        return int(match.group())
    return 0


def normalize_option_type(value):
    value = clean_text(value).upper()
    if value in ["CALL", "CE", "C"]:
        return "CE"
    if value in ["PUT", "PE", "P"]:
        return "PE"
    return value


def normalize_strike_text(strike, option_type):
    option_type = normalize_option_type(option_type)
    strike_no = extract_strike_number(strike)
    if strike_no:
        return f"{strike_no} {option_type}"
    return clean_text(strike)


def contract_key(symbol, expiry, strike, option_type):
    return (
        clean_text(symbol).upper(),
        clean_text(expiry),
        extract_strike_number(strike),
        normalize_option_type(option_type),
    )


def upsert_contract(symbol, expiry, strike, option_type, exchange_id):
    symbol = clean_text(symbol, "NIFTY").upper()
    expiry = clean_text(expiry)
    option_type = normalize_option_type(option_type)
    strike_text = normalize_strike_text(strike, option_type)
    strike_no = extract_strike_number(strike_text)
    exchange_id = clean_text(exchange_id)

    if not symbol or not expiry or not strike_no or option_type not in ["CE", "PE"]:
        return None

    new_contract = {
        "symbol": symbol,
        "expiry": expiry,
        "strike": strike_no,
        "strike_text": strike_text,
        "option_type": option_type,
        "exchange_instrument_id": exchange_id,
    }

    contracts = STATE.setdefault("contracts", [])
    key = contract_key(symbol, expiry, strike_text, option_type)

    for i, c in enumerate(contracts):
        if contract_key(c.get("symbol"), c.get("expiry"), c.get("strike"), c.get("option_type")) == key:
            contracts[i] = new_contract
            return new_contract

    contracts.append(new_contract)
    contracts.sort(key=lambda c: (clean_text(c.get("expiry")), int(c.get("strike") or 0), clean_text(c.get("option_type"))))
    return new_contract


def ensure_contract_from_active(state):
    # If active fields have ID, keep them in the selectable master list.
    contracts = state.setdefault("contracts", [])
    symbol = clean_text(state.get("symbol"), "NIFTY").upper()
    expiry = clean_text(state.get("expiry"))

    for option_type, strike_field, id_field in [
        ("CE", "call_strike", "call_exchange_id"),
        ("PE", "put_strike", "put_exchange_id"),
    ]:
        strike_text = normalize_strike_text(state.get(strike_field, ""), option_type)
        exchange_id = clean_text(state.get(id_field, ""))
        strike_no = extract_strike_number(strike_text)
        if not expiry or not strike_no or not exchange_id:
            continue

        new_contract = {
            "symbol": symbol,
            "expiry": expiry,
            "strike": strike_no,
            "strike_text": strike_text,
            "option_type": option_type,
            "exchange_instrument_id": exchange_id,
        }
        key = contract_key(symbol, expiry, strike_text, option_type)
        found = False
        for i, c in enumerate(contracts):
            if contract_key(c.get("symbol"), c.get("expiry"), c.get("strike"), c.get("option_type")) == key:
                contracts[i] = new_contract
                found = True
                break
        if not found:
            contracts.append(new_contract)

    contracts.sort(key=lambda c: (clean_text(c.get("expiry")), int(c.get("strike") or 0), clean_text(c.get("option_type"))))


def find_contract(symbol, expiry, strike, option_type):
    key = contract_key(symbol, expiry, strike, option_type)
    for c in STATE.get("contracts", []):
        if contract_key(c.get("symbol"), c.get("expiry"), c.get("strike"), c.get("option_type")) == key:
            return c
    return None


STATE = load_state()


# =========================
# DEMO CHART STATE
# =========================
CHART_STATE = {
    "candles": [],
    "last_price": 24250.0
}


def init_demo_candles():
    if CHART_STATE["candles"]:
        return

    now = int(time.time())
    now = now - (now % 300)
    price = 24250.0
    candles = []

    for i in range(90):
        candle_time = now - ((89 - i) * 300)
        open_price = price
        move = random.uniform(-18, 18)
        close_price = open_price + move
        high_price = max(open_price, close_price) + random.uniform(3, 15)
        low_price = min(open_price, close_price) - random.uniform(3, 15)

        candles.append({
            "time": candle_time,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2)
        })
        price = close_price

    CHART_STATE["candles"] = candles
    CHART_STATE["last_price"] = candles[-1]["close"]


def update_demo_last_candle():
    init_demo_candles()
    candles = CHART_STATE["candles"]
    now = int(time.time())
    current_5m_time = now - (now % 300)
    last = candles[-1]

    if current_5m_time > last["time"]:
        new_open = last["close"]
        new_close = new_open + random.uniform(-6, 6)
        candles.append({
            "time": current_5m_time,
            "open": round(new_open, 2),
            "high": round(max(new_open, new_close) + random.uniform(1, 6), 2),
            "low": round(min(new_open, new_close) - random.uniform(1, 6), 2),
            "close": round(new_close, 2)
        })
        if len(candles) > 120:
            candles.pop(0)
        CHART_STATE["last_price"] = candles[-1]["close"]
        return

    tick_move = random.uniform(-4, 4)
    new_close = last["close"] + tick_move
    last["close"] = round(new_close, 2)
    last["high"] = round(max(last["high"], new_close), 2)
    last["low"] = round(min(last["low"], new_close), 2)
    CHART_STATE["last_price"] = last["close"]


# =========================
# ORDER / WEBHOOK HELPERS
# =========================
def add_order(order):
    STATE["orders"].insert(0, order)
    if len(STATE["orders"]) > 100:
        STATE["orders"] = STATE["orders"][:100]
    save_state()


def get_request_json():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    try:
        raw = request.data.decode("utf-8").strip()
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass
    return {}


def parse_tradingview_signal(data):
    order_side = clean_text(data.get("OrderSide")).upper()
    option_type = normalize_option_type(data.get("OptionType"))

    if order_side in ["BUY", "SELL"] and option_type in ["CE", "PE"]:
        if option_type == "CE" and order_side == "BUY":
            log_type = "CALL_BUY"
        elif option_type == "CE" and order_side == "SELL":
            log_type = "CALL_SELL"
        elif option_type == "PE" and order_side == "BUY":
            log_type = "PUT_BUY"
        else:
            log_type = "PUT_SELL"
        return {"ok": True, "option_type": option_type, "order_side": order_side, "log_type": log_type, "mode": "PINE_JSON"}

    raw = clean_text(data.get("action") or data.get("side") or data.get("signal") or data.get("type")).upper().replace(" ", "_")
    if raw in ["BUY", "CALL", "CALL_BUY", "CE", "CE_BUY"]:
        return {"ok": True, "option_type": "CE", "order_side": "BUY", "log_type": "CALL_BUY", "mode": "SIMPLE_TEST"}
    if raw in ["CALL_SELL", "CE_SELL", "CALL_EXIT", "C_EXIT"]:
        return {"ok": True, "option_type": "CE", "order_side": "SELL", "log_type": "CALL_SELL", "mode": "SIMPLE_TEST"}
    if raw in ["SELL", "PUT", "PUT_BUY", "PE", "PE_BUY"]:
        return {"ok": True, "option_type": "PE", "order_side": "BUY", "log_type": "PUT_BUY", "mode": "SIMPLE_TEST"}
    if raw in ["PUT_SELL", "PE_SELL", "PUT_EXIT", "P_EXIT"]:
        return {"ok": True, "option_type": "PE", "order_side": "SELL", "log_type": "PUT_SELL", "mode": "SIMPLE_TEST"}

    return {"ok": False, "message": "Invalid signal. Need Pine JSON with OrderSide/OptionType or action BUY/SELL."}


def get_active_contract(option_type, incoming_data=None):
    incoming_data = incoming_data or {}
    symbol = clean_text(STATE.get("symbol"), "NIFTY").upper()
    expiry = clean_text(STATE.get("expiry"))

    if option_type == "CE":
        strike_text = normalize_strike_text(STATE.get("call_strike", ""), "CE")
        dashboard_exchange_id = clean_text(STATE.get("call_exchange_id"))
    else:
        strike_text = normalize_strike_text(STATE.get("put_strike", ""), "PE")
        dashboard_exchange_id = clean_text(STATE.get("put_exchange_id"))

    matched = find_contract(symbol, expiry, strike_text, option_type)
    contract_exchange_id = clean_text(matched.get("exchange_instrument_id")) if matched else ""
    incoming_exchange_id = clean_text(incoming_data.get("ExchangeInstrumentId"))

    exchange_id = dashboard_exchange_id or contract_exchange_id or incoming_exchange_id
    if dashboard_exchange_id:
        exchange_source = "DASHBOARD_ACTIVE_ID"
    elif contract_exchange_id:
        exchange_source = "CONTRACT_MASTER"
    else:
        exchange_source = "TRADINGVIEW_JSON_ID"

    return {
        "symbol": symbol,
        "expiry": expiry,
        "strike_text": strike_text,
        "strike_price": extract_strike_number(strike_text),
        "option_type": option_type,
        "exchange_id": exchange_id,
        "exchange_source": exchange_source,
    }


def build_broker_payload_from_dashboard(data, option_type, order_side):
    STATE.setdefault("open_positions", {})
    existing_position = STATE["open_positions"].get(option_type)

    if order_side == "SELL" and existing_position:
        strike_price = existing_position.get("StrikePrice")
        exchange_id = existing_position.get("ExchangeInstrumentId")
        qty = existing_position.get("Qty", STATE.get("qty", 65))
        exchange_source = "OPEN_POSITION_MEMORY"
        expiry_value = existing_position.get("Expiry", STATE.get("expiry", data.get("Expiry", "")))
    else:
        contract = get_active_contract(option_type, data)
        strike_price = contract["strike_price"]
        exchange_id = contract["exchange_id"]
        qty = STATE.get("qty", 65)
        exchange_source = contract["exchange_source"]
        expiry_value = STATE.get("expiry") or data.get("Expiry", "")

    payload = {
        "Exchange": data.get("Exchange", "NSEFO"),
        "ExchangeInstrumentId": to_int_if_possible(exchange_id, exchange_id),
        "SymbolName": data.get("SymbolName", STATE.get("symbol", "NIFTY")),
        "SymbolSeries": data.get("SymbolSeries", "OPTIDX"),
        "Expiry": to_int_if_possible(expiry_value, expiry_value),
        "OptionType": option_type,
        "StrikePrice": int(strike_price),
        "OrderSide": order_side,
        "OrderType": data.get("OrderType", "MARKET"),
        "Price": data.get("Price", 0),
        "TriggerPrice": data.get("TriggerPrice", 0),
        "Qty": int(qty),
        "DisclosedQty": data.get("DisclosedQty", 0),
        "source": "TRIMURTI_CAPITAL_DASHBOARD",
        "dashboard_override": True,
        "strategy": STATE.get("strategy", ""),
        "exchange_id_source": exchange_source,
    }
    return payload


def forward_to_old_webhook(payload):
    if not FORWARD_TO_OLD_WEBHOOK:
        return {"forwarded": False, "message": "Forward disabled"}

    old_webhook_url = clean_text(STATE.get("old_webhook_url")) or DEFAULT_OLD_WEBHOOK_URL
    if old_webhook_url in ["", ".", "-", "XXXX"]:
        return {"forwarded": False, "message": "OLD_WEBHOOK_URL empty, demo mode only"}

    if requests is None:
        return {"forwarded": False, "message": "requests library not installed. Run: pip install requests"}

    try:
        res = requests.post(old_webhook_url, json=payload, timeout=8)
        success = 200 <= res.status_code < 300
        return {"forwarded": success, "status_code": res.status_code, "response": res.text[:500]}
    except Exception as e:
        return {"forwarded": False, "message": str(e)}


def build_manual_order(action):
    if action == "BUY":
        contract = get_active_contract("CE")
        side = "CALL_BUY"
    else:
        contract = get_active_contract("PE")
        side = "PUT_BUY"
    scrip = f"{contract['symbol']} {contract['strike_price']} {contract['option_type']}"
    return scrip, side


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/state")
def get_state():
    return jsonify(STATE)


@app.route("/api/save-strike", methods=["POST"])
def save_strike():
    data = request.json or {}
    STATE["symbol"] = clean_text(data.get("symbol"), STATE.get("symbol", "NIFTY")).upper()
    STATE["strategy"] = clean_text(data.get("strategy"), STATE.get("strategy", ""))
    STATE["expiry"] = clean_text(data.get("expiry"), STATE.get("expiry", ""))
    STATE["call_strike"] = normalize_strike_text(data.get("call_strike", STATE.get("call_strike", "")), "CE")
    STATE["put_strike"] = normalize_strike_text(data.get("put_strike", STATE.get("put_strike", "")), "PE")
    STATE["call_exchange_id"] = clean_text(data.get("call_exchange_id"), STATE.get("call_exchange_id", ""))
    STATE["put_exchange_id"] = clean_text(data.get("put_exchange_id"), STATE.get("put_exchange_id", ""))
    STATE["old_webhook_url"] = clean_text(data.get("old_webhook_url"), STATE.get("old_webhook_url", ""))

    try:
        STATE["qty"] = int(data.get("qty", STATE.get("qty", 65)))
    except Exception:
        STATE["qty"] = 65

    if STATE["call_exchange_id"]:
        upsert_contract(STATE["symbol"], STATE["expiry"], STATE["call_strike"], "CE", STATE["call_exchange_id"])
    if STATE["put_exchange_id"]:
        upsert_contract(STATE["symbol"], STATE["expiry"], STATE["put_strike"], "PE", STATE["put_exchange_id"])

    save_state()
    return jsonify({"ok": True, "message": "Active strike saved permanently", "state": STATE})


@app.route("/api/activate", methods=["POST"])
def activate():
    STATE["strategy_active"] = True
    save_state()
    return jsonify({"ok": True, "message": "Strategy Activated", "state": STATE})


@app.route("/api/deactivate", methods=["POST"])
def deactivate():
    STATE["strategy_active"] = False
    save_state()
    return jsonify({"ok": True, "message": "Strategy Deactivated", "state": STATE})


@app.route("/api/manual-order", methods=["POST"])
def manual_order():
    data = request.json or {}
    action = clean_text(data.get("action")).upper()
    if action not in ["BUY", "SELL"]:
        return jsonify({"ok": False, "message": "Invalid manual order action"}), 400

    scrip, side = build_manual_order(action)
    order = {"time": "MANUAL", "scrip": scrip, "type": side, "qty": STATE.get("qty", 65), "price": "MARKET", "status": "DASHBOARD ONLY"}
    add_order(order)
    return jsonify({"ok": True, "message": "Manual order added", "order": order})


@app.route("/api/squareoff", methods=["POST"])
def squareoff():
    STATE["strategy_active"] = False
    order = {"time": "LIVE", "scrip": "ALL POSITIONS", "type": "SQUARE OFF", "qty": 0, "price": "-", "status": "REQUESTED"}
    add_order(order)
    return jsonify({"ok": True, "message": "Square off requested and strategy stopped", "order": order, "state": STATE})


@app.route("/api/add-contract", methods=["POST"])
def add_contract():
    data = request.json or {}
    contract = upsert_contract(
        data.get("symbol") or STATE.get("symbol", "NIFTY"),
        data.get("expiry") or STATE.get("expiry", ""),
        data.get("strike", ""),
        data.get("option_type", ""),
        data.get("exchange_instrument_id", "")
    )
    if not contract:
        return jsonify({"ok": False, "message": "Contract not saved. Check expiry, strike, option type and ID."}), 400
    save_state()
    return jsonify({"ok": True, "message": "Contract saved", "contract": contract, "state": STATE})


@app.route("/api/delete-contract", methods=["POST"])
def delete_contract():
    data = request.json or {}
    idx = data.get("index")
    try:
        idx = int(idx)
        if idx < 0 or idx >= len(STATE.get("contracts", [])):
            raise ValueError("invalid index")
        removed = STATE["contracts"].pop(idx)
        save_state()
        return jsonify({"ok": True, "message": "Contract deleted", "removed": removed, "state": STATE})
    except Exception:
        return jsonify({"ok": False, "message": "Invalid contract index"}), 400


@app.route("/webhook", methods=["POST"])
def webhook():
    data = get_request_json()
    parsed = parse_tradingview_signal(data)
    if not parsed.get("ok"):
        return jsonify({"ok": False, "message": parsed.get("message", "Invalid signal"), "received": data}), 400

    option_type = parsed["option_type"]
    order_side = parsed["order_side"]
    log_type = parsed["log_type"]

    if not STATE.get("strategy_active", False):
        order = {"time": "WEBHOOK", "scrip": "-", "type": "BLOCKED", "qty": 0, "price": "-", "status": "STRATEGY OFF"}
        add_order(order)
        return jsonify({"ok": False, "message": "Strategy is OFF. Signal blocked.", "tradingview_data": data}), 403

    final_payload = build_broker_payload_from_dashboard(data, option_type, order_side)
    scrip = f"{STATE.get('symbol', 'NIFTY')} {final_payload['StrikePrice']} {option_type}"
    forward_result = forward_to_old_webhook(final_payload)

    if forward_result.get("forwarded"):
        status = "FORWARDED"
    elif "status_code" in forward_result:
        status = f"FORWARD ERROR {forward_result.get('status_code')}"
    else:
        status = "DEMO / NOT FORWARDED"

    STATE.setdefault("open_positions", {})
    if order_side == "BUY":
        STATE["open_positions"][option_type] = {
            "ExchangeInstrumentId": final_payload["ExchangeInstrumentId"],
            "StrikePrice": final_payload["StrikePrice"],
            "OptionType": final_payload["OptionType"],
            "Expiry": final_payload["Expiry"],
            "Qty": final_payload["Qty"]
        }
    elif order_side == "SELL":
        STATE["open_positions"].pop(option_type, None)

    order = {"time": "WEBHOOK", "scrip": scrip, "type": log_type, "qty": final_payload["Qty"], "price": "MARKET", "status": status}
    add_order(order)

    return jsonify({
        "ok": True,
        "message": "TradingView JSON received. Dashboard strike used.",
        "mode": parsed["mode"],
        "tradingview_data": data,
        "used_dashboard_scrip": scrip,
        "final_payload": final_payload,
        "forward_result": forward_result,
        "order": order
    })


@app.route("/api/candles")
def get_candles():
    update_demo_last_candle()
    return jsonify(CHART_STATE["candles"])


if __name__ == "__main__":
    app.run(debug=True)
