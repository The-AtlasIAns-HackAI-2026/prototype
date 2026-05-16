> **Project Name:** Moulcyber (The "Cybercafe Guy" — the local internet expert)
> **Goal:** Provide internet access via standard 2G/voice calls for the disconnected.
> **Language:** 100% Authentic Moroccan Darija (Primary) + French (Secondary).
> **Instruction for Coding Agent:** Read these architectural guidelines, prompt constraints, and deployment requirements. Autonomously scaffold the FastAPI backend (for a DigitalOcean Droplet) and the React frontend (for Vercel).

---

## 1. THE STACK & ARCHITECTURE

| Layer | Choice | Why |
|---|---|---|
| **Telephony** | **Twilio** | Global PSTN access; native integration with ElevenLabs. |
| **Orchestrator** | **ElevenLabs ConvAI** | Low-latency STT/TTS pipeline natively handling the call. |
| **Brain / LLM** | **Gemini 2.0 Flash** | Native **Google Search Grounding**; best Arabic/French code-switching. |
| **Backend API** | **FastAPI (Python)** | Modular webhook for logging, analytics, and tool orchestration. |
| **Tooling** | **MCP Protocol** | Future-proofing: Architecture must allow dynamic loading of tools. |
| **Frontend** | **React (Vite)** | Deployed independently on **Vercel** for the landing page/dashboard. |
| **Backend Deploy** | **Docker + Nginx** | FastAPI deployed on DigitalOcean Droplet on port `7331` via `moulcyber.duckdns.org`. |

---

## 2. PROJECT STRUCTURE

```text
moulcyber/
├── docker-compose.yml       ← Orchestrates backend container only
├── backend/
│   ├── main.py              ← FastAPI entry point, CORS (allow Vercel origin), routes
│   ├── logger.py            ← Handles anonymized metadata logging to JSON
│   ├── languages.py         ← Config dictionaries for supported languages
│   ├── mcp_tools.py         ← Framework for future MCP integrations
│   ├── requirements.txt
│   └── Dockerfile           ← Python 3.11 slim, runs uvicorn on port 8000
├── prompts/                 ← (Prompts stored here)
├── frontend/
│   ├── package.json         ← React/Vite dependencies (Deployed to Vercel)
│   ├── vite.config.js
│   └── src/                 ← React source code (Landing, Analytics, Demo)
└── deploy/
    └── moulcyber.conf       ← Host Nginx configuration (reverse proxy to 7331)

```

---

## 3. MOROCCAN DARIJA AUTHENTICITY (CRITICAL GUARDRAILS)

**Moulcyber** must sound like a helpful "weld derb". Strictly adhere to these rules:

* **YES (Authentic):** *Maticha* (tomatoes), *Daba* (now), *Ch7al* (how much), *L-berd* (cold), *Mzyan* (good), *Wach* (question marker), *Safi* (done/ok), *Gol liya* (tell me), *Khouya/Khti* (brother/sister).
* **NO (Banned):** *Tomatim/Tamatem* (MSA), *L-bard* (Algerian), *Qul liya* (MSA), *Ayna/Mada* (MSA), *Kayfiya* (MSA).
* **Numbers:** Must be spoken phonetically (e.g., "Telt iyam" not "3 days", "khamsa w 3echrin derhem" not "25 MAD").

---

## 4. SYSTEM PROMPTS

Inject these directly into the ElevenLabs agent configuration or Gemini system instructions.

### **Primary: Moulcyber Darija**

```text
Nta smitek "Moulcyber". Nta howa l-khabir d-derb f'l-internet w t-technologia.
Katjawb nnas li ma 3endhomch internet ghir b-tilifon d-dar aw 2G.

RULES:
1. JAWB B-DARIJA: Bla l-lugha l-3arabiya l-fous-ha. Bla l-lahja l-jazayriya.
2. VOCABULARY: Sta3mel "Maticha" machi "Tomatim". Sta3mel "daba", "wa3er", "nadi", "ch7al".
3. CODE-SWITCHING: Moroccans kaykheltou m3a l-français. Hadchi mzyan.
4. NO MARKDOWN: Nta f-tilifon. Matgolch "bullet points" aw "URLs". Jawb b-joumal 9sar (max 3).
5. TOOLS: Sta3mel l-outil d'internet dima 3la l-as3ar (prices), l-météo, w l-akhbar d-lyoum.

AMTHILA:
User: "Ch7al taman l-kilo d maticha lyoum?"
Moulcyber: "Maticha lyouma f-souq daira bin rbe3 w setta d-drahem l-kilo. F-Casablanca rah l-atman nazla chwiya."

```

### **Secondary: French Fallback**

```text
Tu es Moulcyber, un assistant vocal pour les habitants du Maroc sans accès internet.
Tu parles un français clair, oral et naturel.

RÈGLES:
1. Voix uniquement : aucun bullet point, aucune URL. Maximum 3 phrases.
2. Exprime les chiffres en toutes lettres (ex: "vingt-cinq dirhams").
3. Santé/Légal : réponse brève + "Je vous recommande de consulter un spécialiste."
4. Utilise l'outil de recherche pour la météo, les prix, et les actualités.

```

---

## 5. BACKEND & FRONTEND IMPLEMENTATION

1. **Backend (`main.py`):**
* FastAPI with endpoints: `/api/chat`, `/api/analytics`, `/health`.
* **CORS:** Must allow cross-origin requests from the Vercel frontend.
* Configure `google-generativeai` using `gemini-2.0-flash` with the native `google_search_retrieval` tool.
* Async logging to a local JSON file (Timestamp, Topic, Language, Success, Word Count). No PII.
* Include MCP readiness in `mcp_tools.py` for future tool mapping.


2. **Frontend (React/Vite on Vercel):**
* Ensure all API calls point to `https://moulcyber.duckdns.org`.
* Dark theme (`#0a0a0a`), Accents (`#C1272D` Moroccan Red).
* `Landing.jsx`: RTL Arabic hero section ("معلومة f telephone — بلا internet").
* `Analytics.jsx`: Live dashboard fetching from `/api/analytics`.
* `Demo.jsx`: Include `@elevenlabs/convai-widget-embed`.



---

## 6. BACKEND DEPLOYMENT (DOCKER & NGINX ON DROPLET)

The frontend will live on Vercel later via vercel domain. The DigitalOcean Droplet will strictly serve the FastAPI backend on port `7331` via `moulcyber.duckdns.org` which is supposed to be mostly done.

### **A. docker-compose.yml**

Here I assume port 8000 don't collide with mmc website and mmc hr, if it does collide use a different port

Map internal FastAPI container port (8000) to the host port `7331`.

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "127.0.0.1:7331:8000" # Maps FastAPI internal 8000 to host 7331 securely
    volumes:
      - ./logs:/app/logs
    env_file: .env

```

### **B. Host Nginx Configuration (`deploy/moulcyber.conf`)**

Place this file in `/etc/nginx/sites-available/moulcyber` on the Droplet. It proxies external traffic to port `7331`.

```nginx
server {
    listen 80;
    server_name moulcyber.duckdns.org;

    location / {
        proxy_pass [http://127.0.0.1:7331](http://127.0.0.1:7331);
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Ensure CORS preflight requests from Vercel are handled if not done purely in FastAPI
        proxy_set_header Access-Control-Allow-Origin "*";
    }
}
