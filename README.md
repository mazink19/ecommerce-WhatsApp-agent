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

The project demonstration covers the FastAPI backend, WhatsApp integration, Gemini-powered agent, product discovery, shopping cart operations, and application testing.

**Watch the project demonstration:**

[Watch Demo Video](https://github.com/user-attachments/assets/125ba400-7996-4c83-9642-ab89534e8a40)

*The video duration should be updated to reflect the final combined recording.*

## Example Conversations

The following examples illustrate how customers interact with the assistant in English and Arabic.

### English Conversation

**Customer:** Show me the available products.

**Assistant:** Here are the products currently available in the store, including their prices and availability.

**Customer:** Add 10 Gaming Mouse to my cart.

**Assistant:** The requested quantity cannot be added because there isn't enough stock available. Would you like to choose a smaller quantity?

**Customer:** Add 2 Gaming Mouse instead.

**Assistant:** I've added 2 Gaming Mouse to your cart successfully.

**Customer:** Show my cart.

**Assistant:** Your cart contains 2 Gaming Mouse. Here's your current subtotal.

**Customer:** Checkout using Cairo – Maadi as my shipping address.

**Assistant:** Your order has been created successfully. Here are your order details and total.

### Arabic Conversation

**Customer:** وريني المنتجات المتاحة.

**Assistant:** دي المنتجات المتاحة حاليًا في المتجر، مع الأسعار والكميات الموجودة في المخزون.

**Customer:** أضف لي ٢ ماوس.

**Assistant:** تمت إضافة ٢ ماوس إلى سلة التسوق بنجاح.

**Customer:** وريني السلة.

**Assistant:** السلة فيها ٢ ماوس. وده إجمالي الطلب الحالي.

**Customer:** أتمم الطلب، عنوان التوصيل المعادي، القاهرة.

**Assistant:** تم إنشاء طلبك بنجاح. إليك تفاصيل الطلب والإجمالي.

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
ecommerce-WhatsApp-agent/
│
├── backend/
│   ├── main.py
│   ├── database.py
│   └── models.py
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

### 1. Clone the repository

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

## Database Setup

The application uses SQLite for persistent store data.

The database is configured through `backend/database.py`.

**Important:** Starting the FastAPI backend initializes the database tables, but it does not automatically populate sample categories and products.

Before testing the assistant, make sure the database contains categories and products with valid names, prices, and stock quantities.

If the database is empty, populate it with sample store data before starting a shopping conversation. Product and category data are required for product discovery, inventory verification, and checkout.

Carts and orders are stored in SQLite and persist across application restarts.

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