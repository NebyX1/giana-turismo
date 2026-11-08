# Contrato de recuperación

La guía Markdown es la fuente de verdad. El índice híbrido utiliza SQLite FTS5,
Granite de 384 dimensiones, Qdrant embebido, fusión RRF y mMARCO sobre un conjunto
limitado de candidatos. Ambos modelos de recuperación se ejecutan en CPU con
ONNX INT8 AVX2 y están fijados por revisión y hash.

La respuesta incluye estado y evidencia; los fallos técnicos devuelven
`SYSTEM_ERROR`, en lugar de presentarse como falta de conocimiento. La capa de
respuesta usa DeepSeek en Ollama Cloud. El sistema conserva el alcance territorial,
la continuidad de conversación y la evaluación de actualidad de las fuentes.
La evidencia obtenida de la web es efímera y no modifica la colección local.

Un índice sólo puede reutilizarse si coinciden la revisión y el hash de Granite,
el tokenizador, el pooling CLS, la normalización, el límite de tokens, la dimensión
y el hash del corpus. No se admite cambiar a otro embedding o reranker por una
variable de entorno.
