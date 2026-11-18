# PLAN.md: WhatsApp E-Commerce AI Agent (CodeMZ Capstone 2026)

Instructions for Codex: build this project milestone by milestone, in order. Do not start a milestone until the previous one's **Exit criteria** pass. Run the listed verification commands at the end of each milestone and fix failures before moving on. Commit after each milestone with the suggested message.

---

## 0. Project summary

An autonomous WhatsApp agent for an e-commerce store. A customer messages in Arabic or English. The agent (Gemini 2.5) understands the intent and calls up to 10 Python tools. The tools call a FastAPI + SQLite store backend over HTTP. The agent can chain several tools in a single turn (multi-tool calling) and returns one unified reply.

```
WhatsApp (neonize)  ->  bot.py  ->  agent.py (Gemini chat per phone)  ->  tools.py (10 functions)  ->  FastAPI backend (SQLite)
   INGRESS                           REASONER                              TOOLS                         BACKEND
```

### Non-negotiable rules (from the spec)

1. **Gemini client must use** `http_options={"api_version": "v1beta"}`.
2. **Zero hallucination:** the agent never states a price, stock level, order status, or total unless it came from a tool result in the current conversation.
3. **Session isolation:** `sessions_customer[phone]` holds one Gemini chat per phone number. Carts are keyed by phone number (`customer_name` = WhatsApp ID).
4. **Language and format:** reply in the customer's language (Arabic or English). Bold prices, order numbers and totals with `*bold*` (WhatsApp syntax). No heavy emoji use.
5. **Multi-tool in one turn:** a compound message must be fully handled without asking the customer to split it up.
6. Exactly **10 tools**, with type hints and docstrings, in `tools.py`.
7. No secrets and no `.db` files in git.

### Target repo layout

```
ecommerce-whatsapp-agent/
├── backend/
│   ├── main.py            # 10 endpoints
│   ├── models.py          # SQLAlchemy models
│   ├── database.py        # SQLite engine/session
│   ├── schemas.py         # Pydantic schemas
│   ├── seed_data.py       # seed categories/products
│   └── ecommerce.db       # generated, gitignored
├── tools.py               # 10 tool functions
├── agent.py               # Gemini brain + sessions_customer
├── bot.py                 # neonize WhatsApp runner
├── chat_simulate.py       # terminal simulator (no phone needed)
├── tests/                 # pytest (backend, tools, agent, sessions)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── PLAN.md
```

---

## Milestone 1: Repo scaffold and backend baseline

**Goal:** a clean repo with a running store backend.

Tasks:
1. Create the layout above, `git init`, and add `.gitignore` (must include `.env`, `*.db`, `__pycache__/`, `.venv/`, neonize session files such as `*.sqlite3` / `session*` / `*.db`).
2. The spec points to a starter backend zip on Google Drive (FastAPI + SQLite + seeded products). **If a `backend/` folder is already present in the repo, use it as is. If not, build the backend yourself in Milestone 2 per the contract below** (the Drive link may not be reachable from your environment; the human can drop the starter in later and you reconcile against the contract).
3. Create `requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pydantic`, `requests`, `python-dotenv`, `google-genai`, `neonize`, `pytest`, `httpx`.
4. Create `.env.example`:
   ```
   GEMINI_API_KEY=
   GEMINI_MODEL=gemini-2.5-flash
   BACKEND_URL=http://localhost:8000
   STORE_NAME=My Store
   ```
5. Create the venv and install dependencies.

**Exit criteria:** `pip install -r requirements.txt` succeeds. The tree matches the layout. `git status` shows no secrets or DB files.
**Commit:** `chore: scaffold project`

---

## Milestone 2: Backend API (the 10 endpoints)

**Goal:** the store backend implements exactly this contract, with real inventory handling.

| # | Method | Path | Notes |
|---|--------|------|-------|
| 1 | GET | `/categories/` | list all categories |
| 2 | GET | `/products/` | query: `keyword`, `category_id`, `in_stock_only`; keyword is a case-insensitive partial match on name/description |
| 3 | GET | `/products/{id}/` | 404 if missing; includes `stock` |
| 4 | GET | `/cart/{name}/` | items + line totals + cart total; empty cart returns an empty list, not an error |
| 5 | POST | `/cart/items/` | body `{customer_name, product_id, quantity}`; 404 unknown product; 400 if quantity > stock; merge quantity if the product is already in the cart |
| 6 | DELETE | `/cart/items/{id}/` | remove one line |
| 7 | DELETE | `/cart/{name}/` | clear the cart |
| 8 | POST | `/orders/checkout/` | body `{customer_name, shipping_address}`; 400 if the cart is empty; **atomic transaction**: verify stock, decrement stock, create order + order items (store a price snapshot), clear the cart; returns `order_id`, items, total, status |
| 9 | GET | `/orders/{id}/` | status + items + total + address; 404 if missing |
| 10 | PUT | `/orders/{id}/cancel/` | only for cancellable statuses (e.g. `pending`/`confirmed`); **restore stock**; 400 if already cancelled/shipped |

Models: `Category`, `Product(id,name,description,price,stock,category_id)`, `CartItem(id,customer_name,product_id,quantity)`, `Order(id,customer_name,shipping_address,total,status,created_at)`, `OrderItem(id,order_id,product_id,quantity,unit_price)`.

Tasks:
1. Implement `models.py`, `database.py`, `schemas.py`, `main.py`, `seed_data.py` (about 6 categories, 30+ products including "Mechanical Keyboard" and "Gaming Mouse" with stock, and at least one product with stock 0 for edge-case testing).
2. Return consistent JSON errors: `{"detail": "..."}` with proper status codes. The tools layer relies on these messages.
3. Write `tests/test_backend.py` with FastAPI `TestClient` and a temp DB, covering: search, add to cart, over-stock rejection, checkout decrements stock, cancel restores stock, double-cancel rejected, empty-cart checkout rejected.

**Exit criteria:** `pytest tests/test_backend.py` is green. `uvicorn backend.main:app --reload` starts and `/docs` shows 10 routes.
**Commit:** `feat(backend): store API with inventory and orders`

---

## Milestone 3: Tools layer (`tools.py`)

**Goal:** 10 plain Python functions that Gemini can introspect to auto-generate schemas.

Required functions and signatures (names and params must match exactly):

```
list_categories() -> dict
search_products(keyword: str = "", category_id: int = 0, in_stock_only: bool = False) -> dict
get_product_details(product_id: int) -> dict
get_customer_cart(customer_name: str) -> dict
add_item_to_cart(customer_name: str, product_id: int, quantity: int = 1) -> dict
remove_cart_item(item_id: int) -> dict
clear_customer_cart(customer_name: str) -> dict
checkout_cart(customer_name: str, shipping_address: str) -> dict
track_order(order_id: int) -> dict
cancel_order(order_id: int) -> dict
```

Rules:
1. Each function has full type hints and a docstring with a one-line purpose, an `Args:` section, and a `Returns:` description. Docstrings must tell the model **when** to use the tool (e.g. "Call this before quoting any price or stock").
2. Read `BACKEND_URL` from env via `python-dotenv`. Use one shared `requests.Session` and a timeout (10s).
3. Never raise to the model. Catch `requests` exceptions and HTTP errors and return `{"success": False, "error": "<human-readable reason>"}`; on success return `{"success": True, ...data}`. This lets the agent explain failures (out of stock, empty cart) instead of crashing.
4. `search_products`: treat `category_id=0` as "no filter" (Gemini function schemas work better with plain defaults than `Optional`).
5. Export `ALL_TOOLS = [list_categories, ..., cancel_order]` (a list of 10).

Tests (`tests/test_tools.py`): run the backend with a test DB (or mock `requests`) and assert each tool's success and failure shape; assert `len(ALL_TOOLS) == 10`; assert every tool has a docstring and annotations.

**Exit criteria:** `pytest tests/test_tools.py` is green.
**Commit:** `feat(tools): 10 documented backend tools`

---

## Milestone 4: Agent brain (`agent.py`), including multi-tool calling

**Goal:** a function `handle_message(phone: str, text: str) -> str` that returns the final reply text.

Tasks:
1. Create the client exactly as required:
   ```python
   from google import genai
   from google.genai import types
   client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                         http_options={"api_version": "v1beta"})
   ```
2. `sessions_customer: dict[str, Chat] = {}`. `get_session(phone)` creates the chat on first use with `client.chats.create(model=GEMINI_MODEL, config=types.GenerateContentConfig(system_instruction=..., tools=ALL_TOOLS, ...))`. Use the SDK's **automatic function calling** so Gemini can chain several tool calls (search, search, add, add, checkout) inside one `send_message` before producing text. Set the max remote calls to about 15 to prevent runaway loops. Temperature about 0.2.
3. Per-phone `threading.Lock` so two rapid messages from the same customer do not interleave.
4. **System instruction** (build per session; it embeds the phone number). It must state:
   - Role: sales assistant for `{STORE_NAME}`.
   - "The customer's ID is `{phone}`. Always pass this exact value as `customer_name` for cart and checkout tools."
   - Zero hallucination: never state price, stock, cart contents, order status or totals without calling the relevant tool this turn or having it in the conversation. If a tool fails, say so honestly.
   - Handle compound requests in one turn. Search all items first, then add, then checkout only if the customer explicitly gave an address and asked to check out.
   - Do not checkout without a shipping address; ask for it. Confirm cart contents before checkout if the customer did not ask to check out explicitly.
   - Out of stock: say so, offer to search alternatives in the same category (call `search_products` with `in_stock_only=True`).
   - Empty cart: say it is empty and offer help instead of calling checkout.
   - Reply in the customer's language; Arabic dialects (including Egyptian) are fine. Format prices, product names, order numbers and totals as `*bold*`. Keep replies short, no heavy emojis.
   - Currency: the spec example uses ج.م (EGP). Use it, and keep it consistent with the backend.
5. **Hardening (recommended):** wrap each tool that takes `customer_name` so the session phone always overrides whatever the model passes (use `functools.wraps` so the schema is preserved). This guarantees cross-customer isolation even if the model errs.
6. Error handling: catch Gemini API errors, return a polite fallback in the customer's last language, and log the exception. Retry once on transient failures (429/5xx) with a short backoff.
7. Truncate or reset very long histories (for example, keep the last N turns) so sessions do not grow without bound.

Tests (`tests/test_agent.py`):
- Session isolation: two phones create two distinct chat objects; carts never mix (use the real backend with a test DB and a stubbed or live model; mark live-model tests with `@pytest.mark.live` and skip when no key).
- Tool-override wrapper forces the session phone.
- Live (optional): the spec's sample compound message produces at least 5 tool calls in one turn and a single reply with the order number.

**Exit criteria:** with the backend running and a key set, `python -c "from agent import handle_message; print(handle_message('2010', 'show me keyboards'))"` returns a grounded answer.
**Commit:** `feat(agent): Gemini agent with multi-tool calling and per-phone sessions`

---

## Milestone 5: Terminal simulator (`chat_simulate.py`)

**Goal:** test the whole flow without a phone. Worth 10 points together with the README.

Tasks:
1. CLI: `python chat_simulate.py --phone 201000000001`. Loop: read input, call `handle_message`, print the reply.
2. `--verbose` flag prints each tool call and result (use the SDK's function-call history, or log from inside the tool wrapper) so the demo shows multi-tool chaining.
3. Commands: `/phone <id>` to switch simulated customers (proves session isolation), `/reset` to clear a session, `/quit`.
4. Support Arabic input and output correctly (UTF-8).

**Exit criteria:** run the spec's sample message ("... الكيبورد الميكانيكال والماوس الجيمينج ... تشيك أوت لعنواني في القاهرة - المعادي"). The verbose log shows 2 searches, 2 adds and 1 checkout in one turn. One reply states the order number and total. The DB stock is reduced.
**Commit:** `feat: terminal chat simulator`

---

## Milestone 6: Agent governance and edge cases

**Goal:** the 15 points for governance. Add scripted scenarios and fix the prompt or tools until they pass.

Scenarios (put them in `tests/scenarios.md` and, where possible, automate them as live tests):
1. Out-of-stock product: honest message plus alternatives.
2. Quantity above stock: report the available quantity, do not add.
3. Empty cart then "checkout": explain it is empty, no order created.
4. Checkout without an address: ask for the address.
5. Cancel an order: stock is restored, and the agent confirms using tool data.
6. Track a non-existent order id: a clear "not found" message, no invention.
7. Price or stock question: the agent must call a tool (assert at least one tool call happened).
8. English customer gets English; Arabic customer gets Arabic; a mid-conversation language switch is followed.
9. Backend down: friendly error, no crash.
10. Off-topic or abusive message: polite redirect to store help.
11. Ambiguous product ("a mouse"): search, and if several match, list options and ask.

**Exit criteria:** every scenario behaves as described; findings are written into `README.md` (a "Behavior" section).
**Commit:** `feat(agent): governance and edge-case handling`

---

## Milestone 7: Live WhatsApp bot (`bot.py`) with neonize

**Goal:** a stable WhatsApp connection with QR login and per-phone routing.

Tasks:
1. Use `neonize` (`NewClient`). Check the installed version's API first (`pip show neonize`, read its README or examples), because event names and message field paths vary by version. Typical pattern:
   - `client = NewClient("store-bot")` (this creates a local session DB file; make sure it is gitignored).
   - Register `@client.event(ConnectedEv)` for a "connected" log, and `@client.event(MessageEv)` for incoming messages.
   - `client.connect()` prints the QR code in the terminal on the first run; later runs reuse the saved session.
2. In the message handler:
   - Ignore messages sent by the bot itself, group messages (unless intentionally supported), status broadcasts, and empty or non-text messages. For media, reply politely that only text is supported.
   - Extract the sender phone (the user part of the sender JID) and the text (`conversation` or `extendedTextMessage.text`).
   - Call `agent.handle_message(phone, text)` and send the reply to the same chat (`client.send_message(chat_jid, reply)`).
3. Handlers may run on threads. The per-phone lock from Milestone 4 handles concurrency. Wrap the handler in try/except so one failure never kills the bot, and log everything with `logging`.
4. Add a typing or presence indicator if the library makes it easy (optional).
5. Graceful startup checks: verify `GEMINI_API_KEY` is set and the backend `/categories/` responds before connecting; print clear errors otherwise.

Tests: unit-test the pure parts (JID-to-phone extraction, message filtering) with fake event objects. The live QR scan is a **manual step for the human**; note it in the README.

**Exit criteria:** the bot starts, prints a QR code, and (after the human scans it) answers a real WhatsApp message through the full pipeline; two different phones keep independent carts.
**Commit:** `feat(bot): neonize WhatsApp gateway`

---

## Milestone 8: Code quality pass (10 points)

Tasks:
1. Docstrings and type hints on every public function in `tools.py`, `agent.py`, `bot.py`.
2. All config via `python-dotenv` and `.env.example`; no hard-coded keys, URLs or model names.
3. Use `logging`, not `print`, in library code.
4. Run `ruff check .` and `ruff format .` (or `black`) if available; remove dead code and unused imports.
5. Confirm there are no circular imports (`tools` -> backend over HTTP only; `agent` -> `tools`; `bot` -> `agent`).
6. Run the full `pytest -q` suite.

**Exit criteria:** lint clean, all non-live tests green.
**Commit:** `refactor: lint, typing, config cleanup`

---

## Milestone 9: Documentation (README.md, 10 points)

README sections:
1. Overview and architecture diagram (the 4 layers).
2. Prerequisites: Python 3.10+, a Gemini API key, a WhatsApp account for the bot.
3. Setup: clone, venv, `pip install -r requirements.txt`, `cp .env.example .env` and fill it in.
4. Seed and run the backend: seed command and `uvicorn backend.main:app --reload`.
5. Run the simulator, with the sample multi-tool message and the expected output.
6. Run the WhatsApp bot, with QR scan steps and session-file notes.
7. The 10-tool table (name, endpoint, purpose).
8. Strict rules (v1beta, zero hallucination, session isolation, language and formatting).
9. Testing (`pytest`, live-test marker).
10. Troubleshooting: `v1beta` function-calling errors, QR expired or re-link, backend not reachable, quota errors.
11. Demo video link placeholder.

**Exit criteria:** a new developer can follow the README from a clean clone to a working simulator session with no other help.
**Commit:** `docs: README and scenarios`

---

## Milestone 10: Final verification and delivery checklist

Codex tasks:
1. Fresh clone test: new venv, install, seed, run backend, run simulator with the sample message, and confirm the order appears and stock decreases.
2. `git ls-files` must NOT contain `.env`, `*.db`, or neonize session files. If any appear, remove them from the index (`git rm --cached`) and fix `.gitignore`.
3. Rubric self-check (100 points):

| Pillar | Pts | Evidence |
|---|---|---|
| Multi-tool calling | 25 | simulator verbose log, one turn with 5 calls |
| Backend integration and data integrity | 20 | stock decrement/restore tests |
| Live WhatsApp via Neonize | 20 | QR login, per-phone isolation |
| Governance and edge cases | 15 | Milestone 6 scenarios |
| Code quality | 10 | typing, docstrings, dotenv, lint |
| Docs and simulator | 10 | README, `chat_simulate.py` |

**Human-only tasks (Codex cannot do these):**
- Create the Gemini API key and put it in `.env`.
- Scan the WhatsApp QR code with a phone.
- Record the 3 to 5 minute demo video: start the backend, scan the QR, send the compound message, show the DB or API update.
- Push to a clean GitHub repository and submit it.

**Commit:** `chore: final verification`

---

## Appendix A: Gemini calls (reference)

```python
chat = client.chats.create(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    config=types.GenerateContentConfig(
        system_instruction=build_system_prompt(phone),
        tools=ALL_TOOLS,                      # plain Python functions
        temperature=0.2,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            maximum_remote_calls=15
        ),
    ),
)
reply = chat.send_message(text).text
```

If your installed `google-genai` version names these options differently, check its docs and adapt, but keep `api_version="v1beta"`.

## Appendix B: Definition of done

- Sample compound message produces one reply and one order in a single turn.
- Stock decreases on checkout and is restored on cancel.
- Two phone numbers never share a cart.
- Every price, stock level or order number in a reply traces back to a tool result.
- Repo is clean, documented, and secret-free.