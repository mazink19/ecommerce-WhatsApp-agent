# E-Commerce WhatsApp AI Sales Assistant

An AI-powered WhatsApp sales assistant that enables customers to browse products, check availability, manage shopping carts, and place orders through natural language conversations.

The system uses Google Gemini 2.5 Flash by default, with Gemini 3.5 Flash-Lite available as an alternative. It connects to a FastAPI backend and SQLite database through Python tools.

## Features

- **Product discovery:** Search products by name, description, or category.
- **Live inventory verification:** Check current prices and stock before making claims.
- **Shopping cart management:** Add products and retrieve cart contents.
- **Checkout:** Collect shipping addresses and create orders.
- **Order management:** Retrieve order details and cancel orders.
- **WhatsApp integration:** Receive and respond to customer messages using Neonize.
- **Customer isolation:** Maintain separate carts and conversations for different WhatsApp customers.
- **Multilingual support:** Handle Arabic and English messages, including Arabic transliterations of English product names.
- **Safe tool execution:** Prevent silent quantity reductions and avoid inventing product or order information.
- **Gemini integration:** Uses Gemini 2.5 Flash by default, with Gemini 3.5 Flash-Lite as an alternative.


## Demo Video

Watch the project demonstration:

https://github.com/user-attachments/assets/56ab9575-84ad-46bf-b46b-af524b75fc32


### English conversation

**Customer:** Show me the available products.

**Assistant:** Here are the products currently available in the store...

**Customer:** Add 2 Gaming Mouse to my cart.

**Assistant:** I've added 2 Gaming Mouse to your cart.

**Customer:** Show my cart.

**Assistant:** Your cart contains 2 Gaming Mouse. Here's your current subtotal...

### Arabic conversation

**Customer:** وريني المنتجات المتاحة.

**Assistant:** يعرض المساعد المنتجات المتاحة حاليًا من قاعدة بيانات المتجر.

**Customer:** أضف لي ٢ ماوس.

**Assistant:** يتعرف المساعد على المنتج والكمية، ويتحقق من المخزون قبل الإضافة.

*These are illustrative conversation examples, not captured production transcripts.*

## Architecture

The application follows four architectural layers.

1. **Ingress Layer — WhatsApp / Neonize**
   - Receives incoming WhatsApp messages.
   - Identifies customers by their WhatsApp identifiers.
   - Sends responses back to customers.

2. **Reasoning Layer — AI Agent**
   - Uses Gemini 2.5 Flash by default.
   - Maintains separate in-memory conversation sessions.
   - Determines which tools are needed to fulfill customer requests.

3. **Tools Layer — Python**
   - Provides functions for product searches, stock verification, cart operations, and order management.
   - Connects the AI agent to the backend.

4. **Backend Layer — FastAPI / SQLite**
   - Exposes the store API.
   - Handles business logic and database operations.
   - Persists products, categories, carts, and orders.

### Request Flow

```text
WhatsApp Customer
       |
       v
Neonize (bot.py)
       |
       v
AI Agent (agent.py)
       |
       v
Google Gemini
       |
       v
Python Tools (tools.py)
       |
       v
FastAPI Backend
       |
       v
SQLite Database
```

## Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Default AI Model | Gemini 2.5 Flash |
| Alternative AI Model | Gemini 3.5 Flash-Lite |
| Gemini Client | Google GenAI SDK |
| Backend | FastAPI |
| Database | SQLite |
| ORM | SQLAlchemy |
| WhatsApp Integration | Neonize |
| Testing | Pytest |
| Code Quality | Ruff |
| Package Management | uv |

## Prerequisites

Before running the project, install:

- Python 3.12 or newer.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python dependency and environment management.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey).
- A WhatsApp account for QR pairing. A separate account is recommended for testing.
- An internet connection for Gemini API and WhatsApp connectivity.

## Project Structure

```text
ecommerce-whatsapp-agent/
│
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   └── ecommerce.db
│
├── tests/
│   ├── test_agent.py
│   ├── test_backend.py
│   └── scenarios.md
│
├── agent.py
├── tools.py
├── bot.py
├── simulate_chat.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

## Installation and Setup

### 1. Get the project

Open the project repository and clone it using its GitHub URL:

```bash
git clone https://github.com/mazink19/ecommerce-WhatsApp-agent.git
cd ecommerce-WhatsApp-agent
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment variables

Create a `.env` file in the project root using `.env.example` as a template.

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash


MAX_TOOL_CALLS_PER_TURN=8

BACKEND_URL=http://localhost:8000

STORE_NAME=My Store
```

### Environment Variables

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model name |
| `MAX_TOOL_CALLS_PER_TURN` | Maximum tool calls allowed per conversation turn |
| `BACKEND_URL` | FastAPI backend URL |
| `STORE_NAME` | Store name used by the assistant |

Keep `.env` and WhatsApp authentication/session files out of version control. Never commit API keys or authentication credentials.

## Running the Application

The backend and WhatsApp bot run as separate processes.

### 1. Start the backend

From the project root:

```bash
uv run uvicorn backend.main:app --reload
```

Backend URL:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

### 2. Try the agent without WhatsApp

The project includes `simulate_chat.py` for testing conversations directly from the terminal.

```bash
uv run python simulate_chat.py
```

This allows you to evaluate agent behavior without connecting a WhatsApp account.

### 3. Start the WhatsApp bot

Open another terminal:

```bash
uv run python bot.py
```

Follow the QR pairing instructions displayed in the terminal to connect WhatsApp.

Keep the bot running to receive and respond to messages.

## Database

The application uses SQLite for persistent store data.

The database is configured through `backend/database.py`. If the database does not contain the required sample categories and products, populate it before testing the assistant.

Carts and orders are stored in SQLite and survive application restarts.

## Conversation Sessions

The agent maintains conversation sessions in memory, separately for each customer.

Restarting the WhatsApp bot resets the in-memory conversation history. However, persistent cart and order records remain in SQLite.

## Testing

Run the complete test suite:

```bash
uv run pytest -q
```

Run Ruff:

```bash
uv run ruff check .
```

The test suite covers agent behavior, backend API contracts, quantity validation, customer isolation, and conversation scenarios.

Detailed scenario expectations are documented in `tests/scenarios.md`.

## Known Limitations

- **Conversation persistence:** Conversation history is stored in memory and resets when the agent process restarts.
- **Payments:** The application does not currently integrate a payment gateway.
- **Database:** SQLite is used instead of a production database server.
- **WhatsApp connection:** The bot requires an active WhatsApp connection and valid authentication session.
- **Tool limits:** Tool execution is bounded by `MAX_TOOL_CALLS_PER_TURN`.

## License

No license has been specified yet. A license should be selected before distributing this repository publicly. Until then, do not assume that others have permission to reuse or redistribute the code.