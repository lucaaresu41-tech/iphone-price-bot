#!/usr/bin/env python3
"""
Bot Telegram che monitora il prezzo dell'iPhone 17 Pro 256 GB Arancione cosmico su Amazon.it.

Pensato per girare su GitHub Actions (gratis, anche a PC spento): ad ogni esecuzione
controlla i prezzi, aggiorna lo storico in data/prices.json e manda notifiche su Telegram.

Variabili d'ambiente:
  TELEGRAM_TOKEN    token del bot (da @BotFather)
  TELEGRAM_CHAT_ID  il tuo chat id (vedi get_chat_id.py)
  TARGET_PRICE      (opzionale) soglia in euro, es. 1150
  FORCE_SUMMARY     (opzionale) "1" per forzare l'invio del riepilogo
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
STATE_FILE = ROOT / "data" / "prices.json"
TZ = ZoneInfo(CONFIG.get("timezone", "Europe/Rome"))

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
_target = os.environ.get("TARGET_PRICE", "").strip() or CONFIG.get("target_price")
TARGET_PRICE = float(str(_target).replace(",", ".")) if _target not in (None, "") else None

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
]

BLOCKED = "blocked"  # Amazon ha mostrato un captcha / pagina anti-bot: si salta il controllo


# --------------------------------------------------------------------------- utilità
def now() -> dt.datetime:
    return dt.datetime.now(TZ)


def eur(x) -> str:
    if x is None:
        return "n/d"
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def parse_price(text: str):
    """'1.179,00 €' -> 1179.0"""
    if not text:
        return None
    t = re.sub(r"[^\d,\.]", "", text)
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") == 1 and len(t.split(".")[1]) == 3:  # "1.179" = migliaia
        t = t.replace(".", "")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- Telegram
def tg(method: str, **kwargs):
    if not TOKEN:
        print(f"[telegram disattivato] {method}: {kwargs.get('data', {}).get('text', '')}")
        return None
    try:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", timeout=30, **kwargs)
        if not r.ok:
            print(f"Errore Telegram {method}: {r.status_code} {r.text[:300]}")
        return r.json() if r.ok else None
    except requests.RequestException as e:
        print(f"Errore Telegram {method}: {e}")
        return None


def send(text: str, chat_id: str | None = None):
    print("→ Telegram:", text.replace("\n", " | "))
    tg("sendMessage", data={
        "chat_id": chat_id or CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })


def send_photo(png: bytes, caption: str, chat_id: str | None = None):
    tg("sendPhoto", data={"chat_id": chat_id or CHAT_ID, "caption": caption, "parse_mode": "HTML"},
       files={"photo": ("grafico.png", png, "image/png")})


# --------------------------------------------------------------------------- Amazon
def fetch(asin: str):
    """Ritorna (html, errore). In caso di captcha non insiste: salta e riprova al giro successivo."""
    url = f"https://www.amazon.it/dp/{asin}?th=1&psc=1"
    err = None
    for attempt in range(3):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            r = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException as e:
            err = f"errore di rete: {e}"
            time.sleep(5)
            continue
        low = r.text.lower()
        if "captcha" in low and "productTitle" not in r.text:
            return None, BLOCKED
        if r.status_code == 200:
            return r.text, None
        if r.status_code == 404:
            return None, "pagina non trovata (404)"
        err = f"HTTP {r.status_code}"
        time.sleep(5 + attempt * 5)  # errori temporanei del server
    return None, err


def extract(html: str, asin: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.select_one("#productTitle")
    title = " ".join(title_el.get_text().split()) if title_el else ""

    landed = soup.select_one("input#ASIN")
    landed_asin = landed.get("value") if landed else asin
    # Se la variante richiesta non è in vendita, Amazon apre un'altra variante (es. 1 TB):
    if landed_asin and landed_asin != asin:
        return {"available": False, "price": None, "title": title,
                "note": "variante non disponibile su Amazon in questo momento"}

    price = None
    for sel in ("#corePriceDisplay_desktop_feature_div", "#corePrice_feature_div",
                "#apex_desktop", "#corePrice_desktop"):
        box = soup.select_one(sel)
        if not box:
            continue
        candidates = box.select(".priceToPay, .apex-pricetopay-value") or box.select(".a-price")
        for p in candidates:
            # salta prezzo barrato / "prezzo consigliato"
            if "a-text-price" in (p.get("class") or []) or p.get("data-a-strike") or p.find_parent(class_="a-text-price"):
                continue
            off = p.select_one(".a-offscreen")
            price = parse_price(off.get_text() if off else "")
            if price is None:
                whole = p.select_one(".a-price-whole")
                frac = p.select_one(".a-price-fraction")
                if whole:
                    w = re.sub(r"[^\d]", "", whole.get_text())  # "1.739," -> "1739"
                    f = re.sub(r"[^\d]", "", frac.get_text()) if frac else "00"
                    price = parse_price(f"{w},{f or '00'}") if w else None
            if price:
                break
        if price:
            break

    if price is None:
        m = re.search(r'"priceAmount"\s*:\s*([0-9]+(?:\.[0-9]+)?)', html)
        if m:
            price = float(m.group(1))

    avail_el = soup.select_one("#availability")
    avail_txt = " ".join(avail_el.get_text().split()) if avail_el else ""
    unavailable = "non disponibile" in avail_txt.lower() or "currently unavailable" in avail_txt.lower()

    seller_el = soup.select_one("#sellerProfileTriggerId") or soup.select_one(
        "#merchantInfoFeature_feature_div .offer-display-feature-text-message")
    seller = " ".join(seller_el.get_text().split()) if seller_el else ""

    return {
        "available": bool(price) and not unavailable,
        "price": price if not unavailable else None,
        "title": title,
        "seller": seller,
        "note": avail_txt[:120] if avail_txt else "",
    }


# --------------------------------------------------------------------------- grafico
def make_chart(state: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=120)
    plotted = False
    for p in CONFIG["products"]:
        s = state.get(p["asin"])
        if not s:
            continue
        pts = [(dt.datetime.fromisoformat(h["t"]), h["price"]) for h in s.get("history", [])]
        if not pts:
            continue
        pts.append((now(), pts[-1][1]))  # estende la linea fino ad oggi
        xs = [x for x, _ in pts]
        ys = [y if y is not None else float("nan") for _, y in pts]
        if all(y != y for y in ys):  # tutti NaN
            continue
        ax.step(xs, ys, where="post", label=p["name"][:45], linewidth=2)
        plotted = True
    if not plotted:
        plt.close(fig)
        return None
    if TARGET_PRICE:
        ax.axhline(TARGET_PRICE, color="green", linestyle="--", linewidth=1, label=f"Soglia {eur(TARGET_PRICE)}")
    ax.set_title("iPhone 17 Pro 256 GB Arancione – prezzo Amazon.it")
    ax.set_ylabel("€")
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m", tz=TZ))
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def status_text(state: dict, header: str) -> str:
    lines = [header]
    for p in CONFIG["products"]:
        s = state.get(p["asin"], {})
        url = f"https://www.amazon.it/dp/{p['asin']}"
        cur = s.get("last_price") if s.get("available") else None
        lines.append(f"\n<b>{p['name']}</b>")
        lines.append(f"Ora: <b>{eur(cur)}</b>" + ("" if s.get("available") else " (non disponibile)"))
        if s.get("min_price"):
            lines.append(f"Minimo storico: {eur(s['min_price'])} ({s.get('min_date', '')[:10]})")
        if s.get("max_price"):
            lines.append(f"Massimo storico: {eur(s['max_price'])}")
        lines.append(f'<a href="{url}">Apri su Amazon</a>')
    if TARGET_PRICE:
        lines.append(f"\n🎯 Soglia impostata: {eur(TARGET_PRICE)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- comandi Telegram
def handle_commands(state: dict):
    """Legge i messaggi inviati al bot dall'ultima esecuzione (/prezzo, /grafico, /start)."""
    if not TOKEN:
        return
    meta = state.setdefault("_meta", {})
    res = tg("getUpdates", data={"offset": meta.get("tg_offset", 0), "timeout": 0})
    if not res or not res.get("ok"):
        return
    for upd in res.get("result", []):
        meta["tg_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip().lower()
        if not chat or chat != CHAT_ID:
            continue  # risponde solo a te
        if text.startswith("/prezzo") or text.startswith("/start"):
            send(status_text(state, "📱 <b>Stato attuale</b>"), chat)
        elif text.startswith("/grafico"):
            png = make_chart(state)
            if png:
                send_photo(png, "📈 Andamento prezzo", chat)
            else:
                send("Non ci sono ancora abbastanza dati per il grafico.", chat)


# --------------------------------------------------------------------------- main
def main():
    state = load_state()
    meta = state.setdefault("_meta", {})
    ts = now().isoformat(timespec="minutes")
    any_ok = False
    blocked = 0

    for p in CONFIG["products"]:
        asin, name = p["asin"], p["name"]
        url = f"https://www.amazon.it/dp/{asin}"
        s = state.setdefault(asin, {"history": []})

        html, err = fetch(asin)
        if err:
            print(f"[{asin}] salto: {err}")
            blocked += err == BLOCKED
            continue
        info = extract(html, asin)
        any_ok = True
        price = info["price"] if info["available"] else None
        print(f"[{asin}] {name}: {eur(price)}  {info.get('note', '')}")

        prev_price = s.get("last_price")
        prev_avail = s.get("available")
        first_run = prev_avail is None

        # storico: si salva un punto solo quando qualcosa cambia
        if first_run or price != prev_price or info["available"] != prev_avail:
            s["history"].append({"t": ts, "price": price})
        s["last_check"] = ts
        s["available"] = info["available"]
        if price is not None:
            s["last_price"] = price

        old_min = s.get("min_price")
        if price is not None:
            if old_min is None or price < old_min:
                s["min_price"], s["min_date"] = price, ts
            if price > s.get("max_price", 0):
                s["max_price"] = price

        # ---- notifiche
        link = f'\n<a href="{url}">👉 Apri su Amazon</a>'
        if first_run:
            send(f"🤖 Monitoraggio avviato!\n<b>{name}</b>\nPrezzo attuale: <b>{eur(price)}</b>"
                 + ("" if info["available"] else f"\n⚠️ {info.get('note') or 'non disponibile'}") + link)
            continue

        if info["available"] and not prev_avail:
            send(f"✅ <b>Di nuovo disponibile!</b>\n{name}\nPrezzo: <b>{eur(price)}</b>" + link)
        elif not info["available"] and prev_avail:
            send(f"⚠️ Non più disponibile: {name}" + link)
        elif price is not None and prev_price is not None and price != prev_price:
            diff = price - prev_price
            pct = diff / prev_price * 100
            if diff < 0 and CONFIG.get("notify_on_any_drop", True):
                extra = "\n🏆 <b>Nuovo minimo storico!</b>" if old_min is None or price < old_min else ""
                send(f"📉 <b>Prezzo sceso!</b>\n{name}\n{eur(prev_price)} → <b>{eur(price)}</b> "
                     f"({diff:+.2f} €, {pct:+.1f}%)" + extra + link)
            elif diff > 0 and CONFIG.get("notify_on_rise", False):
                send(f"📈 Prezzo salito\n{name}\n{eur(prev_price)} → <b>{eur(price)}</b> ({pct:+.1f}%)" + link)

        # soglia: avvisa quando si scende sotto (una volta, finché non torna sopra)
        if TARGET_PRICE and price is not None:
            if price <= TARGET_PRICE and not s.get("below_target"):
                send(f"🎯 <b>Sotto la tua soglia di {eur(TARGET_PRICE)}!</b>\n{name}\nPrezzo: <b>{eur(price)}</b>" + link)
                s["below_target"] = True
            elif price > TARGET_PRICE:
                s["below_target"] = False

        time.sleep(random.uniform(3, 8))  # pausa tra una pagina e l'altra

    # ---- gestione blocchi prolungati di Amazon
    if any_ok:
        if meta.get("block_notified"):
            send("✅ Il controllo dei prezzi funziona di nuovo.")
        meta["consecutive_fail"] = 0
        meta["block_notified"] = False
    else:
        meta["consecutive_fail"] = meta.get("consecutive_fail", 0) + 1
        if meta["consecutive_fail"] >= 6 and not meta.get("block_notified"):
            send("⚠️ Da alcune ore Amazon non risponde ai controlli automatici"
                 + (" (pagina anti-bot)" if blocked else "") + ". Continuo a riprovare.")
            meta["block_notified"] = True

    # ---- riepilogo giornaliero
    hour = CONFIG.get("daily_summary_hour")
    today = now().date().isoformat()
    force = os.environ.get("FORCE_SUMMARY") == "1"
    if force or (hour is not None and now().hour >= int(hour) and meta.get("last_summary") != today):
        meta["last_summary"] = today
        text = status_text(state, f"☀️ <b>Riepilogo del {now():%d/%m/%Y}</b>")
        png = make_chart(state)
        if png and len(text) <= 1000:
            send_photo(png, text)
        else:
            send(text)
            if png:
                send_photo(png, "📈 Andamento prezzo")

    handle_commands(state)
    save_state(state)


if __name__ == "__main__":
    if not TOKEN or not CHAT_ID:
        print("ATTENZIONE: TELEGRAM_TOKEN / TELEGRAM_CHAT_ID mancanti: i messaggi verranno solo stampati.",
              file=sys.stderr)
    main()
