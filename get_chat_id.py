#!/usr/bin/env python3
"""Trova il tuo TELEGRAM_CHAT_ID.

1. Apri il tuo bot su Telegram e scrivigli un messaggio qualsiasi (es. "ciao").
2. Lancia:  python3 get_chat_id.py IL_TUO_TOKEN
"""
import json
import sys
import urllib.request

if len(sys.argv) != 2:
    sys.exit("Uso: python3 get_chat_id.py IL_TUO_TOKEN")

url = f"https://api.telegram.org/bot{sys.argv[1].strip()}/getUpdates"
data = json.load(urllib.request.urlopen(url))
chats = {}
for u in data.get("result", []):
    chat = (u.get("message") or {}).get("chat")
    if chat:
        chats[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
if not chats:
    print("Nessun messaggio trovato: scrivi qualcosa al bot su Telegram e riprova.")
for cid, name in chats.items():
    print(f"TELEGRAM_CHAT_ID = {cid}   ({name})")
