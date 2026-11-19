# 📱 Bot Telegram – prezzo iPhone 17 Pro 256 GB Arancione (Amazon.it)

Controlla Amazon.it **ogni 5 minuti** (il minimo di GitHub; a volte qualche minuto di ritardo) e ti scrive su Telegram **ogni volta che il prezzo cambia**:
- 📉 il prezzo **scende** (con 🏆 se è il nuovo minimo storico)
- 📈 il prezzo **sale**
- ✅ il prodotto **torna disponibile** / ⚠️ non è più disponibile
- 🎯 il prezzo va **sotto la tua soglia** (opzionale)
- ☀️ ogni mattina alle 9: **riepilogo con grafico** dell'andamento

Gira **gratis su GitHub Actions**: funziona anche con il PC spento.

Prodotti monitorati (modificabili in `config.json`):
| ASIN | Cosa è |
|---|---|
| `B0FQFQ7544` | iPhone 17 Pro 256 GB Arancione cosmico, **nuovo** (scheda ufficiale Apple su Amazon) |

---

## Messa online (circa 10 minuti)

### 1. Crea il bot Telegram
1. Su Telegram cerca **@BotFather** e invia `/newbot`.
2. Scegli un nome (es. `Prezzo iPhone`) e uno username che finisca in `bot` (es. `luca_iphone_prezzi_bot`).
3. BotFather ti dà un **token** tipo `123456789:AAF...`. Copialo e **non condividerlo**.
4. Apri il tuo nuovo bot e scrivigli un messaggio qualsiasi (es. `ciao`).

### 2. Trova il tuo Chat ID
Da Terminale, nella cartella del progetto:
```bash
python3 get_chat_id.py IL_TUO_TOKEN
```
Ti stampa `TELEGRAM_CHAT_ID = 12345678`.

### 3. Carica il progetto su GitHub
1. Crea un account gratuito su https://github.com (se non ce l'hai).
2. Crea un nuovo repository: **New repository** → nome `iphone-price-bot` → **Public** → **Create**.
   (Public = minuti di Actions illimitati. Lo storico prezzi sarà visibile, ma token e chat id restano segreti.)
3. Da Terminale, nella cartella del progetto:
   ```bash
   git remote add origin https://github.com/TUO_USERNAME/iphone-price-bot.git
   git push -u origin main
   ```
   Se ti chiede la password, usa un *Personal Access Token* (GitHub → Settings → Developer settings → Tokens).

### 4. Inserisci i segreti
Nel repository: **Settings → Secrets and variables → Actions**
- Scheda **Secrets** → *New repository secret*:
  - `TELEGRAM_TOKEN` = il token di BotFather
  - `TELEGRAM_CHAT_ID` = il numero del punto 2
- (Opzionale) Scheda **Variables** → *New repository variable*:
  - `TARGET_PRICE` = es. `1150` → ti avvisa quando il prezzo scende sotto questa cifra

### 5. Avvia
**Actions** → abilita i workflow se richiesto → **Monitor prezzo iPhone** → **Run workflow**.
Entro un minuto ricevi su Telegram "🤖 Monitoraggio avviato!". Da lì in poi parte da solo ogni 5 minuti.

---

## Comandi Telegram
Scrivi al bot `/prezzo` (stato attuale) o `/grafico` (andamento).
⚠️ Il bot non è sempre acceso, quindi risponde al **controllo successivo**, cioè entro pochi minuti.
Per una risposta immediata: Actions → Run workflow.

## Personalizzazioni (`config.json`)
- `daily_summary_hour`: ora del riepilogo (`null` = disattivato)
- `notify_on_rise`: `false` se non vuoi gli avvisi quando il prezzo sale
- `products`: aggiungi altri ASIN (il codice dopo `/dp/` nel link Amazon)
- Frequenza: in `.github/workflows/monitor.yml`, ad esempio `"*/15 * * * *"` = ogni 15 minuti

## Note
- Se Amazon mostra una pagina anti-bot, il controllo viene **saltato** e si riprova al giro successivo.
  Se succede per 3 ore di fila ricevi un avviso.
- GitHub sospende i workflow programmati dopo **60 giorni senza attività nel repository**. Il bot salva un commit
  almeno una volta al giorno, quindi resta attivo da solo. Se si ferma, basta premere "Enable workflow" in Actions.
- Lo storico prezzi è in `data/prices.json`.
