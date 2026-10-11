# npa_chat

**Owner:** WS4 (Chatbot)

Multilingual (en/ta/hi) hardship chatbot. `ChatEngine.handle(session_id, customer_id, req) -> BotReply`
(see `npa_contracts.providers.ChatEngineProtocol`). Numbers in customer text come only from
the rules engine. CI uses `MockLLMClient` (no network).

**Tasks:** 4.1 dialogue engine · 4.2 hardship & affordability · 4.3 offer flow · 4.4 zero-capacity path · 4.5 complaint capture · 4.6 guardrails

> Bootstrap stub created by WS5. The owner replaces this README with: purpose, public API,
> how to run, and which RBI/BIS items the package implements (A9).
