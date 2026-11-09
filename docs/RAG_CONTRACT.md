# Contrato RAG

Corpus preservado en Markdown. La recuperación combina fast path estructurado, SQLite FTS5, Granite 384d en CUDA, RRF, mMARCO en CUDA sólo sobre candidatos pequeños y segunda oportunidad limitada a tres consultas. La respuesta siempre incluye estado y evidencia; los fallos técnicos son `SYSTEM_ERROR`, nunca ausencia de conocimiento. Web requiere consentimiento ligado a sesión y request, y no contamina Qdrant.
