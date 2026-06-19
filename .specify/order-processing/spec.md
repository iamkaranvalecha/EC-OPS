Building an Order Processing System

Objective:
The goal of this assignment is to design, implement, and test a backend system in any language (Python, .NET etc) that handles order processing efficiently.

Scenario:
You have been hired to build the backend for an E-commerce Order Processing System. The system should allow customers to place orders, track their status, and support basic order operations.

Requirements

1. Core Features
  - Create an order: Customers should be able to place an order with multiple items.
  - Retrieve order details: The system should allow fetching order details by order ID.
  - Update order status: The order should have statuses like PENDING, PROCESSING, SHIPPED, and DELIVERED. A background job should automatically update PENDING orders to PROCESSING every 5 minutes.
  - List all orders: Retrieve all orders, optionally filtered by status.
  - Cancel an order: Customers should be able to cancel an order, but only if it's still in PENDING status.

2. I'd also like to extend core features to be used via APIs and Agentic AI through rich chat interface to execute same operations with MCP, A2A and AG-UI + A2UI protocols working together.

3. Vector retrieval provisions (future-ready, stubbed now):
   - Enable pgvector PostgreSQL extension at database setup time.
   - Create an order_embeddings table (order_id FK, embedding vector(1536), content text) to support future semantic search over order history.
   - Provide ingestion stub: a function that generates and stores embeddings for an order's items (called after create_order, no-op until an embedding model is wired).
   - Provide retrieval stub: a function that accepts a natural-language query and returns the top-K semantically similar orders (returns empty list until embedding model is wired).
   - Expose a search_orders MCP tool stub so the tool surface is established for future agentic semantic retrieval.
