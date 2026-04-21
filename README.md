# # Smart Spend AI - Personal Finance Multi-Agent System

AI-powered personal finance backend with multi-agent architecture and comprehensive security protection.

## Features

- 💬 **Chat Interface** - Natural language expense tracking and financial advice
- 🤖 **Multi-Agent System** - Specialized agents for categorization, insights, education
- 🔒 **Security Protection** - Multi-layer security against SQL injection, XSS, prompt injection
- 📊 **Spending Insights** - AI-powered financial analysis and recommendations
- 📚 **Financial Education** - Knowledge base for financial literacy
- 🔐 **Authentication** - Secure user authentication with JWT

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
pip install psycopg2-binary  # PostgreSQL driver
```

### 2. Configure Environment

```bash
# Copy and edit environment files
cp .env.example .env
cp security.env.example security.env

# Edit .env with your database and API keys
# Edit security.env with security settings
```

### 3. Run the Application

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

### Basic Config (.env)
- `DATABASE_URL` - PostgreSQL connection string
- `OPENAI_API_KEY` - OpenAI API key (optional)
- `OLLAMA_BASE_URL` - Ollama local LLM (default: http://localhost:11434)
- `SECRET_KEY` - JWT secret key

### Security Config (security.env)
- `SECURITY_LEVEL` - basic, standard, or strict
- `ENABLE_SQL_GUARD` - SQL injection protection
- `ENABLE_XSS_GUARD` - XSS protection
- `ENABLE_PROMPT_GUARD` - Prompt injection protection
- `ENABLE_LEAK_GUARD` - Information leak prevention
- `ENABLE_LLM_SECURITY_CHECK` - LLM-assisted detection
- `SECURITY_LLM_MODEL` - LLM model for security checks

## API Endpoints

- `POST /api/chat` - Chat with financial assistant
- `POST /api/transactions` - Record transactions
- `GET /api/insights` - Get spending insights
- `POST /api/education` - Financial education Q&A
- `POST /api/upload` - Upload receipts/statements
- `GET /health` - Health check

## Security Features

### Multi-Layer Protection
1. **Regex Layer** - Fast pattern matching (<1ms)
2. **LLM Layer** - Semantic analysis (2-5s, only for suspicious inputs)

### Protected Against
- ✅ SQL Injection
- ✅ XSS Attacks
- ✅ Prompt Injection
- ✅ Information Leakage
- ✅ Input/Output Sanitization

## Tech Stack

- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - Database ORM
- **PostgreSQL** - Primary database
- **OpenAI/Ollama** - LLM integration
- **SentenceTransformers** - Text embeddings

## Project Structure

```
├── agents/           # Multi-agent system
│   ├── security/     # Security agent (new)
│   ├── categorization/
│   ├── insights/
│   ├── education/
│   └── chat_routing/
├── api/              # API endpoints
├── models/           # Database models
├── schemas/          # Pydantic schemas
├── data/             # Knowledge base
└── scripts/          # Utility scripts
```

## Testing

Run tests:
```bash
pytest tests/
```

## License

MIT