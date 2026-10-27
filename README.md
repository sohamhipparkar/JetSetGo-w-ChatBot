# JetSetGo + Policy Chatbot

JetSetGo now has the **Flight Policy Assistant chatbot** built in: a floating "Ask JetSetGo" chat on every
page, plus a new **Travel Policy** page at `/travel-policy`.

The chatbot is the **same engine** as the Flight Policy Assistant (`policybot`, model `gemini-2.5-flash`),
running on the default policy rebranded for JetSetGo. Only names and contact details changed; every rule,
number and clause is identical, so it answers exactly like the assistant does on the default policy. It
still has every Air Canada safeguard:

- every claim must quote a real clause word-for-word (checked in code)
- a second Gemini pass audits the answer for contradictions
- no promises or approvals ("you will get a refund")
- unverifiable answers fall back to the policy's exact text
- prompt-injection attempts are blocked
- every Q&A is written to `backend/logs/audit_log.jsonl`

```
JetSetGo/
├── frontend/                      React + Vite + Tailwind website (existing)
│   ├── src/data/jetsetgo_policy.md   ← THE policy (used by the website page AND the chatbot)
│   ├── src/components/PolicyChatbot.jsx   chat widget (added to every page via App.jsx)
│   ├── src/components/TravelPolicy.jsx    /travel-policy page
│   ├── src/lib/policyApi.js       calls the backend
│   ├── src/lib/miniMarkdown.jsx   safe formatting for answers
│   └── vite.config.js             proxies /api → backend in development
└── backend/                       Python API (new)
    ├── server.py                  Flask API: POST /api/chat, GET /api/health
    ├── policybot/                 same engine as flight-policy-assistant
    ├── evaluate.py                30 Air Canada questions → logs/evaluation_results.csv
    └── tests/                     22 offline tests
```

There is **one policy file**: the backend reads `frontend/src/data/jetsetgo_policy.md`, so the page and
the chatbot can never disagree. Edit that file to change the policy, then restart the backend.

---

## Run it (Windows + VS Code, two terminals)

### Terminal 1: backend (the chatbot brain)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

You should see `JetSetGo policy chatbot API on http://localhost:8000`.
Check it at <http://localhost:8000/api/health>. `"api_key_configured": true` means the key was found.

**API key:** the backend reads `GEMINI_API_KEY` from `backend/.env`. If that file doesn't exist, it uses the
key already in `frontend/.env`. The key is only read on the server and is never sent to the browser. The
cleaner setup is to copy `backend/.env.example` to `backend/.env`, paste the key there, and delete it from
`frontend/.env`.

### Terminal 2: website

```bash
cd frontend
npm install          # only needed once (no new packages were added)
npm run dev
```

Open <http://localhost:5173>, then click the round chat button in the bottom-right corner.

---

## Testing

```bash
cd backend
python -m pytest -q        # 22 offline tests (fake model, no API key needed)
python evaluate.py         # LIVE: 30 Air Canada questions → logs/evaluation_results.csv
python evaluate.py 1 7 27  # run only some questions
```

`evaluation_results.csv` opens in Excel with columns **Question / Expected output / Actual output / Status /
Clauses cited / Result**, ready to paste into a report.

---

## ⚠️ Website text that contradicts the policy (an Air Canada risk)

The chatbot answers only from the Travel Policy. But some existing pages say something different, and in the
Air Canada ruling the airline was held to whatever its website said. These pages need updating to match the
policy (they weren't changed in this integration):

| Page | Says | Policy says |
|---|---|---|
| `Help.jsx` FAQ | Checked bag "up to 15kg" | Depends on fare; Flex 23 kg, Business 2 × 32 kg (2.4, 2.5) |
| `Help.jsx` article | Online check-in opens 48 hours before | Opens 24 hours before, closes 90 min before (11.1) |
| `FAQ.jsx` cancellation | Cancellations 24h+ before departure get refund/credit; Basic can be changed for a fee | Depends on fare; Basic cannot be changed after the 24-hour window (2.2, 2.3) |
| `FAQ.jsx` pets | Larger animals travel in the cargo hold | JetSetGo does **not** carry pets in the cargo hold (14.3) |

The Travel Policy page also shows clause 1.4: if anything conflicts, customers should confirm with Customer
Care before travelling.

---

## Deploying

- **Frontend (Vercel):** unchanged. Set the environment variable `VITE_API_URL` to your backend's URL.
- **Backend:** any Python host (Render, Railway, a VM). Start command: `gunicorn server:app` (in `backend/`).
  Set `GEMINI_API_KEY`, and set `ALLOWED_ORIGINS` to your site's URL (e.g. `https://jetsetgo.vercel.app`).
- The backend has a basic rate limit (20 questions/minute per visitor) to protect your Gemini quota.
