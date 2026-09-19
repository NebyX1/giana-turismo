# Arquitectura

M0/M1 mantienen un único backend Flask propietario de los modelos CUDA, Qdrant para dense retrieval y SQLite FTS5 para lexical retrieval. Pipecat conecta VAD Silero, Moonshine español CPU, el procesador RAG y Piper HTTP CPU. SmallWebRTC es el transporte de desarrollo; LiveKitTransport se selecciona en el runner final. Un `generation_id` cancela respuestas y audio obsoletos durante barge-in.
