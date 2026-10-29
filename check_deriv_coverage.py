"""One-off diagnostic: checks how many of bias_bot.py's 55 instruments are
actually available on Deriv's free public feed, and under what symbol code.

Run via the companion workflow (check_deriv.yml) or locally with:
    pip install websocket-client
    python check_deriv_coverage.py

Prints a report, split into MATCHED (display name -> Deriv symbol code) and
NOT FOUND, so we know exactly what can move off Yahoo Finance onto Deriv's
faster, direct feed, and what (if anything) has to stay on Yahoo.
"""
import json
import os

import websocket

DERIV_URL = os.environ.get("DERIV_WS_URL", "wss://ws.derivws.com/websockets/v3?app_id=1089")

# display_name (as used in bias_bot.py's PAIRS) -> search keyword(s) to try
# against Deriv's active_symbols list.
TARGETS = {
    # forex majors
    "AUDUSD": "AUD/USD", "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD", "NZDUSD": "NZD/USD",
    "USDCAD": "USD/CAD", "USDCHF": "USD/CHF", "USDJPY": "USD/JPY",
    # forex crosses
    "AUDCAD": "AUD/CAD", "AUDCHF": "AUD/CHF", "AUDJPY": "AUD/JPY", "AUDNZD": "AUD/NZD",
    "CADCHF": "CAD/CHF", "CADJPY": "CAD/JPY", "CHFJPY": "CHF/JPY", "EURAUD": "EUR/AUD",
    "EURCAD": "EUR/CAD", "EURCHF": "EUR/CHF", "EURGBP": "EUR/GBP", "EURJPY": "EUR/JPY",
    "EURNZD": "EUR/NZD", "GBPAUD": "GBP/AUD", "GBPCAD": "GBP/CAD", "GBPCHF": "GBP/CHF",
    "GBPJPY": "GBP/JPY", "NZDCAD": "NZD/CAD", "NZDCHF": "NZD/CHF", "NZDJPY": "NZD/JPY",
    # metals
    "XAGUSD": "Silver", "XAUUSD": "Gold",
    # commodities
    "NATGAS": "Natural Gas", "UKOIL": "Brent", "USOIL": "Oil/USD",
    # indices
    "AUS200": "Australia", "FRA40": "France", "GER40": "Germany",
    "HK50": "Hong Kong", "JPN225": "Japan", "UK100": "UK 100",
    "US100": "Tech 100", "US30": "Wall Street", "US500": "US 500",
    # crypto
    "ADAUSDT": "Cardano", "ARBUSDT": "Arbitrum", "AVAXUSDT": "Avalanche",
    "BCHUSDT": "Bitcoin Cash", "BNBUSDT": "BNB", "BTCUSDT": "Bitcoin",
    "DOGEUSDT": "Dogecoin", "ETCUSDT": "Ethereum Classic", "ETHUSDT": "Ethereum",
    "LINKUSDT": "Chainlink", "LTCUSDT": "Litecoin", "SOLUSDT": "Solana",
    "XRPUSDT": "XRP",
    # synthetic - already known
    "VIX25": "Volatility 25",
}


def fetch_active_symbols():
    ws = websocket.create_connection(DERIV_URL, timeout=20)
    try:
        ws.send(json.dumps({"active_symbols": "brief", "product_type": "basic"}))
        data = json.loads(ws.recv())
    finally:
        ws.close()
    if "error" in data:
        raise RuntimeError(data["error"].get("message"))
    return data.get("active_symbols", [])


def main():
    symbols = fetch_active_symbols()
    matched, missing = [], []

    for display_name, keyword in TARGETS.items():
        needle = keyword.lower().replace(" ", "").replace("/", "")
        hits = [
            s for s in symbols
            if keyword.lower() in s.get("display_name", "").lower()
            or needle in s.get("symbol", "").lower()
        ]
        if hits:
            # Prefer the shortest/cleanest symbol if several variants match.
            best = min(hits, key=lambda s: len(s.get("symbol", "")))
            matched.append((display_name, best["symbol"], best["display_name"]))
        else:
            missing.append(display_name)

    print(f"\n=== MATCHED on Deriv ({len(matched)}/{len(TARGETS)}) ===")
    for name, sym, disp in sorted(matched):
        print(f"  {name:<10} -> deriv:{sym:<15} ({disp})")

    print(f"\n=== NOT FOUND on Deriv ({len(missing)}/{len(TARGETS)}) - stays on Yahoo ===")
    for name in sorted(missing):
        print(f"  {name}")


if __name__ == "__main__":
    main()
