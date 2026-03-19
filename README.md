# ProductAI-agent
Build product fastAPI AI-agent to plan a tour (find and book flight, book hotel, recommend attractive destination and activities(food, culture)). Design a travel planning system that leverages user preferences, travel history, chat history, and weather api, with human-in-the-loop validation for hotel booking actions. Code using Python, FastAPI, LangGraph, and LangChain, RAG (Retrieval-Augmented Generation).

## 💬 Where to ask questions
Please use our dedicated channels for questions and discussion. Help is much more valuable if it's shared publicly so that more people can benefit from it.

| Type                            | Platforms      |
| ------------------------------- |----------------|
| 🚨 **Bug Reports**              | [GitHub Issue] |
| 🎁 **Feature Requests & Ideas** | [GitHub Issue] |
| 🗯 **General Discussion**       | [Linkedin] or [Gitter Room] |

[GitHub issue]: https://github.com/trungtruc123/itiner-aiagent/issues
[github discussions]: https://github.com/trungtruc123/itiner-aiagent/issues
[gitter room]: https://www.facebook.com/profile.php?id=100038801181933
[linkedin]: https://www.linkedin.com/in/truc-tran-trung-380533149/


## 🔗 Links and Resources
| Type                                  | Links                                                                                            |
|---------------------------------------|--------------------------------------------------------------------------------------------------|
| 💼 **FastAPI**                        | [ReadTheDocs](https://fastapi.tiangolo.com/tutorial/)                                            
| 💾 **LangGraph**                      | [LangGraph](https://github.com/langchain-ai/langgraph)                                           |
| 👩‍💻 **PostgresSQL & pgvector**      | [pgvector](https://github.com/pgvector/pgvector)                                                 |
| 💾 **Langfuse**                       | [Langfuse](https://github.com/langfuse/langfuse)                                                 |
| 👩‍💻 **Learn AI-agent for beginner** | [Learn ai-agent](https://github.com/microsoft/ai-agents-for-beginners)                           |
| 📌 **Road Map**                       | [Main Development Plans](https://github.com/trungtruc123/product_aiagent/blob/develop/README.md) 

## 🌟 Features

- **Production-Ready Architecture**

  - Uses **LangGraph** for building stateful, multi-step AI agent workflows
  - Uses **FastAPI** for high-performance async REST API endpoints
  - Integrates **Langfuse** for LLM observability and tracing
  - Uses **mem0" and PostgresSQL include (pgvector, graph Neo4j, redis cache) for save memory (shot-term memory, long-term memory) 
  - Uses RAG(Retrieval-Augmented Generation) to answer questions about each hotel's specific regulations and policies.
  - When booking a hotel, user confirmation is required before proceeding with the reservation (Human-in-loop in workfollow)
  - Implements **JWT authentication** with session management
  - Provides **rate limiting** with slowapi
  - Includes **Prometheus metrics** and **Grafana dashboards** for monitoring
  - Uses **structlog** for structured logging with environment-specific formatting
  - Implements **retry logic** using tenacity library
  - Uses **rich** library for colored, formatted console outputs


- **Long-Term Memory**

  Design a memory system for an AI agent that leverages Mem0 and PostgreSQL (with pgvector) combined with a Neo4j graph database and Redis cache to store and manage both short-term and long-term memory. The goal is to build a robust memory architecture for AI agents that can remember user preferences, past interactions, and contextual knowledge over time.Use `Mem0` as the core memory orchestration layer.Store long-term memory in PostgreSQL with `pgvector` for semantic search and retrieval.
    - Represent relationships and contextual connections using `Neo4j` (graph-based memory).
    - Utilize `Redis` as a caching layer for short-term memory and fast access to recent interactions.
    - Support efficient retrieval, updating, and ranking of memories based on relevance and recency.
    - Enable hybrid search combining vector similarity (pgvector) and graph traversal (Neo4j).
    - Ensure scalability, low latency, and consistency across all memory components.
    - Store memories per user_id for personalized experiences
    - Use async methods: `add()`, `get()`, `search()`, `delete()`
    - Configure memory collection name via environment variables


- **RAG (Retrieval-Augmented Generation)**

  Design a question-answering system that uses RAG (Retrieval-Augmented Generation) to provide accurate and context-aware responses about each hotel's specific regulations and policies.
  The system should:
  
    - Retrieve relevant documents (e.g., hotel policies, rules, FAQs) from a knowledge base using semantic search.
    - Use a vector database to store and index hotel-specific information.
    - Ensure responses are grounded in retrieved data to avoid hallucinations.
    - Support queries about policies such as check-in/check-out times, cancellation rules, pet policies, and additional fees.
    - Provide precise, reliable, and explainable answers based only on the retrieved context.
  
  Allow easy updates when hotel policies change.

- **Security**

  - JWT-based authentication
  - Session management
  - Input sanitization ( help prevent XSS and other injection attacks)
  - CORS configuration
  - Rate limiting protection

- **Developer Experience**

  - Environment-specific configuration with automatic .env file loading
  - Comprehensive logging system with context binding
  - Clear project structure following best practices
  - Type hints throughout for better IDE support
  - Easy local development setup with Makefile commands
  - Automatic retry logic with exponential backoff for resilience

- **Evaluation**
  - Automated metric-based evaluation of model outputs
  - Integration with Langfuse for trace analysis
  - Detailed JSON reports with success/failure metrics
  - Interactive command-line interface
  - Customizable evaluation metrics

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- PostgreSQL ([see Database setup](#database-setup))
- Docker and Docker Compose (optional)

### Environment Setup

1. Clone the repository:

```bash
git clone <repository-url>
cd <project-directory>
```

2. Create and activate a virtual environment:
First install uv (uv == setup.py + requirement.txt)```pip install uv ```
```bash
uv sync
```

3. Copy the example environment file:

```bash
cp .env.example .env.[development|staging|production] # e.g. .env.development
```

4. Update the `.env` file with your configuration (see `.env.example` for reference)

### Database setup

1. Create a PostgreSQL database (e.g Supabase or local PostgreSQL)
2. Update the database connection settings in your `.env` file:

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=travel_planner
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

### Running the Application

#### Local Development

1. Install dependencies:

```bash
uv sync
```

2. Run the application:
- window:
```bash
uv run uvicorn app.main:app --reload 
```
- linux or mac:
```bash
uv run uvicorn app.main:app --reload
```
1. Go to Swagger UI:

```bash
http://localhost:8000/docs
```

## 🔧 Configuration

The application uses a flexible configuration system with environment-specific settings:

- `.env.development` - Local development settings
- `.env.staging` - Staging environment settings
- `.env.production` - Production environment settings
