"""Pipecat local voice pipeline. SmallWebRTC is the development transport."""
import asyncio
import json
import os
import time
import traceback
import uuid
from enum import StrEnum
from pathlib import Path
import aiohttp
import httpx

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import InterruptionFrame, LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame, TTSAudioRawFrame, TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame, VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.turns.user_start import VADUserTurnStartStrategy
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy
from pipecat.turns.user_turn_processor import UserTurnProcessor
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.services.moonshine.stt import Model, MoonshineSTTService
from pipecat.services.piper.tts import PiperHttpTTSService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transcriptions.language import Language
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame

from voice.agent import GenerationController
from voice.trace import trace_event

ROOT = Path(__file__).resolve().parents[1]
VOICE_DIAGNOSTICS = os.getenv("GIANA_DIAGNOSTICS", "false").lower() == "true"
VOICE_COUNTERS_PATH = ROOT / "run" / "voice_counters.json"
CURRENT_TTS_TRACE = {"session_id": "", "turn_id": "", "generation_id": ""}
CURRENT_TURN_DEBUG = {"session_id": "", "turn_id": "", "generation_id": ""}

# Watchdog de última defensa: si SmartTurn ya decidió COMPLETE y Moonshine
# nunca entregó el transcript final, reportamos el error ESPECÍFICO.  NO es un
# mecanismo normal de finalización, sólo diagnóstico.  (El timeout genérico de
# 25 s del frontend queda como red final, nunca como flujo normal.)
TRANSCRIPT_ARRIVAL_WATCHDOG_SECS = 2.5
# Si SmartTurn dice INCOMPLETE pero el usuario ya calló, Pipecat cierra el
# turno por este timeout; 3 s evita esperas largas antes de responder.
USER_TURN_STOP_TIMEOUT_SECS = 3.0

# Debe reflejar los mismos términos que WEB_FOLLOWUP en backend/app/intent_router.py.
_WEB_REQUEST_TERMS = ("buscá en la web", "busca en la web", "buscar en la web", "en internet", "web")


def _looks_like_web_request(text: str) -> bool:
    q = text.lower()
    return any(term in q for term in _WEB_REQUEST_TERMS)


class TurnPhase(StrEnum):
    """Estados explícitos de un user turn.  La finalización es una función
    pura del estado, independiente del orden en que lleguen SmartTurn y
    Moonshine: ``try_finalize_turn`` re-evalúa en cada evento."""

    SPEECH = "SPEECH"
    ANALYZING_END = "ANALYZING_END"
    WAITING_TRANSCRIPT = "WAITING_TRANSCRIPT"
    COMPLETE_PENDING = "COMPLETE_PENDING"
    FINALIZED = "FINALIZED"


class TurnState:
    """Barrera de finalización por user turn (sección 2 del brief).

    Guarda la decisión de SmartTurn aunque el transcript todavía no haya
    llegado, y viceversa: guarda el transcript aunque SmartTurn todavía no
    haya decidido.  ``try_finalize_turn`` es el ÚNICO autorizado a finalizar.
    """

    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self.speech_active = True
        self.smart_turn_decision: str | None = None
        self.transcript_segments: list[str] = []
        self.transcript_ready = False
        self.finalized = False
        self.backend_dispatched = False
        self.backend_dispatch_count = 0
        self.phase = TurnPhase.SPEECH
        self.session_id = ""
        self.generation_id: str | None = None
        self.grace_task: asyncio.Task | None = None
        # generation de la respuesta assistant; se crea recién al finalizar
        # el turno (sección 12): nunca cancelamos la generación que acabamos
        # de crear con el propio barge-in del usuario.
        self.assistant_generation_id: str | None = None

    @property
    def text(self) -> str:
        return " ".join(self.transcript_segments).strip()

    def transcript_arrived(self, text: str) -> bool:
        value = " ".join(text.split()).strip()
        if not value:
            return False
        if self.transcript_segments and (value == self.transcript_segments[-1] or self.transcript_segments[-1].endswith(value)):
            return False
        if self.transcript_segments and value.startswith(self.transcript_segments[-1]):
            self.transcript_segments[-1] = value
            return True
        self.transcript_segments.append(value)
        return True

    def as_dict(self) -> dict:
        return {"turn_id": self.turn_id, "phase": self.phase.value if isinstance(self.phase, TurnPhase) else str(self.phase), "speech_active": self.speech_active, "smart_turn_decision": self.smart_turn_decision, "transcript_ready": self.transcript_ready, "transcript_segments": len(self.transcript_segments), "finalized": self.finalized, "backend_dispatched": self.backend_dispatched}


class UserTurnBuffer:
    """Ordered transcript segments for one semantic user turn."""

    def __init__(self):
        self.segments: list[str] = []

    def reset(self):
        self.segments.clear()

    def append(self, text: str) -> bool:
        value = " ".join(text.split()).strip()
        if not value:
            return False
        if self.segments and (value == self.segments[-1] or self.segments[-1].endswith(value)):
            return False
        if self.segments and value.startswith(self.segments[-1]):
            self.segments[-1] = value
            return True
        self.segments.append(value)
        return True

    @property
    def text(self) -> str:
        return " ".join(self.segments).strip()


class AssistantResponseBuffer:
    """Canonical assistant response shared by UI text and TTS input."""

    def __init__(self, generation_id: str):
        self.generation_id = generation_id
        self.parts: list[str] = []

    def append(self, text: str):
        if text:
            self.parts.append(text)

    def finalize(self) -> str:
        return "".join(self.parts).strip()


def normalized_text(value: str) -> str:
    return " ".join(value.replace("…", "...").split()).strip().lower()


def human_session_dir() -> Path | None:
    marker = ROOT / "logs" / "test" / "CURRENT_HUMAN_TURN_SESSION.txt"
    if not marker.exists():
        return None
    try:
        return Path(marker.read_text(encoding="utf-8").strip())
    except OSError:
        return None


def write_turn_record(record: dict):
    session_dir = human_session_dir()
    if not session_dir or not record.get("turn_id"):
        return
    try:
        turns = session_dir / "turns"
        turns.mkdir(parents=True, exist_ok=True)
        (turns / f"{record['turn_id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def completion_guard_delay(text: str) -> tuple[float, str]:
    normalized = " ".join(text.lower().split())
    cues = (" y", " pero", " porque", " entonces", " además", " por ejemplo", "quiero", "estoy buscando", "necesito", "algo como", "un lugar donde", "y también")
    if normalized.endswith(("...", "…")) or any(normalized.endswith(cue) for cue in cues):
        return 1.1, "long_or_incomplete_cue"
    if len(normalized) < 34 and ("?" in normalized or normalized.endswith((".", "!"))):
        return 0.3, "short_complete"
    if len(normalized) > 90 or normalized.count(" y ") >= 1:
        return 0.85, "multi_clause"
    return 0.65, "normal"


class TracedSmartTurnAnalyzer(LocalSmartTurnAnalyzerV3):
    """Pipecat Smart Turn with production diagnostics, still local CPU-only."""

    async def analyze_end_of_turn(self):
        started = time.perf_counter()
        trace_event("turn", "smart_turn_analysis_started", **CURRENT_TURN_DEBUG, detail="LocalSmartTurnAnalyzerV3 cpu_count=1")
        state, result = await super().analyze_end_of_turn()
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        decision = getattr(state, "name", str(state)).upper()
        trace_event("turn", "smart_turn_result", **CURRENT_TURN_DEBUG, detail=decision, smart_turn=decision, smart_turn_inference_ms=elapsed, elapsed_ms=elapsed)
        # El TurnAnalyzerUserTurnStopStrategy sólo emite UserStoppedSpeakingFrame
        # cuando la decisión es COMPLETE (wait_for_transcript=False), así que
        # dejarla aquí es redundante pero hace el estado explícito y observable
        # para el debugger y los tests.
        LAST_SMART_TURN_DECISION["decision"] = decision
        return state, result


# Última decisión de SmartTurn observada en este proceso de voz.  La usa el
# procesador para dejar explícito el estado del turno (sección 7 del brief).
LAST_SMART_TURN_DECISION = {"decision": ""}


def bump_voice_counter(name):
    if not VOICE_DIAGNOSTICS:
        return
    VOICE_COUNTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(VOICE_COUNTERS_PATH.read_text(encoding="utf-8")) if VOICE_COUNTERS_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[name] = int(data.get(name, 0)) + 1
    VOICE_COUNTERS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class GianaRAGProcessor(FrameProcessor):
    def __init__(self, backend_url="http://localhost:5000", **kwargs):
        super().__init__(**kwargs)
        self.backend_url = backend_url.rstrip("/")
        self.controller = GenerationController(f"session-{uuid.uuid4().hex[:10]}")
        self.turn_state = "LISTENING"
        # Barrera de finalización: estado explícito por user turn.
        self.turn: TurnState | None = None
        self.turn_records: dict[str, dict] = {}
        self._tasks = set()
        self._finalizing = False
        self._transcript_watchdog_task: asyncio.Task | None = None
        self._grace_task: asyncio.Task | None = None
        # Sección 13: generation assistant ACTIVA (despacho en curso).  El
        # barge-in cancela únicamente ésta, nunca la del turno que empieza.
        self._active_assistant_generation_id: str | None = None
        self.http_client = httpx.AsyncClient(base_url=self.backend_url, timeout=httpx.Timeout(60.0, connect=3.0, read=60.0))

    def _task_done(self, task):
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error:
            generation = self.controller.current
            trace_event("voice", "voice_task_exception", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id, status="error", detail=f"{type(error).__name__}: {error}")
            print(traceback.format_exc(), flush=True)

    async def _notify_frontend(self, event: str, payload: dict):
        """Server-message RTVI: única vía por la que el frontend sabe que el
        backend recibió la pregunta.  RETRIEVING ya no se muestra por el solo
        hecho de ver el transcript (sección 9 del brief)."""
        try:
            await self.push_frame(RTVIServerMessageFrame(data={"type": "giana-turn-event", "event": event, **payload}), FrameDirection.DOWNSTREAM)
        except Exception as exc:
            trace_event("voice", "rtvi_notify_failed", status="error", detail=f"{type(exc).__name__}: {exc}")

    def _cancel_scheduled_tasks(self, reason: str):
        tasks = [self._transcript_watchdog_task, self._grace_task]
        if self.turn is not None:
            tasks.append(self.turn.grace_task)
            self.turn.grace_task = None
        for task in tasks:
            if task and not task.done():
                task.cancel()
        self._transcript_watchdog_task = None
        self._grace_task = None
        self._finalizing = False

    async def process_frame(self, frame, direction):
        # Keep Pipecat's system-frame lifecycle (StartFrame creates the
        # processor queue used for ordinary frames) before handling the RAG
        # application frames below.  Without this delegation, a custom
        # FrameProcessor override accepts StartFrame but never initializes its
        # internal processing queue, so STT frames stop at the queue boundary.
        await super().process_frame(frame, direction)
        if type(frame).__name__ in {"StartFrame", "TranscriptionFrame", "InterruptionFrame", "EndFrame", "CancelFrame"}:
            trace_event("voice", "rag_process_frame_enter", detail=f"type={type(frame).__name__} direction={getattr(direction, 'name', direction)}")
        if type(frame).__name__ == "TranscriptionFrame":
            trace_event("voice", "rag_transcription_frame_seen", detail=f"type={type(frame).__module__}.{type(frame).__name__} finalized={getattr(frame, 'finalized', None)} direction={getattr(direction, 'name', direction)} text={getattr(frame, 'text', '')}")
        if isinstance(frame, InterruptionFrame):
            generation = self.controller.current
            turn = self.turn
            if turn and not turn.finalized and turn.phase in (TurnPhase.COMPLETE_PENDING, TurnPhase.WAITING_TRANSCRIPT):
                self._cancel_scheduled_tasks("speech resumed during grace")
                turn.phase = TurnPhase.SPEECH
                turn.speech_active = True
                trace_event("turn", "completion_guard_cancelled", session_id=generation.session_id, turn_id=turn.turn_id, generation_id=generation.generation_id, detail="speech resumed during grace")
            trace_event("voice", "interruption_received", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id)
            # Sección 13: barge-in cancela SOLO la generación assistant activa
            # de turnos ANTERIORES (despacho en curso).  La generación del
            # turno que empieza todavía NO existe, así que jamás se cancela a
            # sí misma (bug previo: turn_started X → generation_cancelled X).
            cancelled_generation_id = self._active_assistant_generation_id
            if cancelled_generation_id:
                await self.controller.interrupt()
                self._active_assistant_generation_id = None
                trace_event("turn", "generation_cancelled", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=cancelled_generation_id, detail="barge-in/user start", cancelled_generation_id=cancelled_generation_id, new_turn_id=turn.turn_id if turn else "")
            else:
                trace_event("turn", "generation_cancel_skipped", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id, detail="no active assistant generation to cancel")
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, VADUserStartedSpeakingFrame):
            generation = self.controller.current
            trace_event("turn", "vad_speech_started", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id, detail=f"start_secs={frame.start_secs}", vad="SPEECH")
        if isinstance(frame, VADUserStoppedSpeakingFrame):
            generation = self.controller.current
            trace_event("turn", "vad_speech_stopped", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id, detail=f"stop_secs={frame.stop_secs}", vad="SILENCE")
        if isinstance(frame, UserStartedSpeakingFrame):
            turn = self.turn
            resume_same_turn = turn is not None and not turn.finalized and turn.text and turn.phase in (TurnPhase.COMPLETE_PENDING, TurnPhase.WAITING_TRANSCRIPT)
            if resume_same_turn:
                # Barge-in durante grace/watchdog del MISMO turno semántico:
                # el usuario siguió hablando.  Reabrimos el turno, conservando
                # el texto ya transcripto.  No hay dispatch previo (turno no
                # finalizado), así que no cancelamos ninguna generación.
                self._cancel_scheduled_tasks("speech resumed same turn")
                turn.speech_active = True
                turn.phase = TurnPhase.SPEECH
                trace_event("turn", "speech_resumed", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail="same semantic turn")
            else:
                # Turno NUEVO: turn_id nuevo.  La generación assistant de
                # respuesta de este turno todavía NO existe (sección 12) — se
                # crea recién al finalizar.
                self._cancel_scheduled_tasks("new user turn")
                generation = self.controller.start()
                turn = TurnState(generation.turn_id)
                turn.session_id = generation.session_id
                turn.generation_id = generation.generation_id
                self.turn = turn
                self.turn_state = "SPEECH"
                CURRENT_TURN_DEBUG.update(session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id)
                trace_event("turn", "turn_started", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id, detail="VADUserTurnStartStrategy")
                self.turn_records[turn.turn_id] = {"turn_id": turn.turn_id, "generation_id": turn.generation_id, "user_segments": [], "user_final_text": "", "turn_state_history": [turn.phase.value], "smart_turn_results": [], "assistant_final_text": "", "tts_segments": [], "tts_full_text": "", "error": None, "timings": {}}
                write_turn_record(self.turn_records[turn.turn_id])
        if isinstance(frame, UserStoppedSpeakingFrame):
            turn = self.turn
            if turn is None or turn.finalized:
                trace_event("turn", "turn_stopped_ignored", detail="no active turn or already finalized")
                return
            turn.speech_active = False
            self.turn_state = "COMPLETE_PENDING"
            turn.phase = TurnPhase.ANALYZING_END
            trace_event("turn", "complete_pending", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=f"speech_active={turn.speech_active} smart_turn={turn.smart_turn_decision} transcript_ready={turn.transcript_ready}", smart_turn=turn.smart_turn_decision or "PENDING", transcript_ready=turn.transcript_ready)
            # SmartTurn COMPLETE viaja dentro del UserStoppedSpeakingFrame
            # (wait_for_transcript=False): la estrategia TurnAnalyzer sólo emite
            # el frame cuando la decisión fue COMPLETE.  El stop-timeout global
            # del UserTurnProcessor (6 s) también puede emitirlo sin decisión;
            # en ese caso respetamos la decisión observada del analyzer.
            observed = LAST_SMART_TURN_DECISION.get("decision") or "COMPLETE"
            if observed != "COMPLETE":
                # UserStoppedSpeakingFrame ya es la decisión final de Pipecat
                # (stop-timeout): sin COMPLETE, el turno igual debe cerrarse.
                trace_event("turn", "turn_stop_timeout_accepted", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=f"stop without COMPLETE decision (observed={observed}); finalizing on stop timeout")
            turn.smart_turn_decision = "COMPLETE"
            turn.phase = TurnPhase.WAITING_TRANSCRIPT if not turn.transcript_ready else TurnPhase.COMPLETE_PENDING
            if not turn.transcript_ready:
                trace_event("turn", "turn_waiting_transcript", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail="SmartTurn COMPLETE antes que transcript; guardando decisión", smart_turn="COMPLETE", transcript="PENDING")
            await self.try_finalize_turn(turn, source="user_stopped_speaking")
            return
        if isinstance(frame, TranscriptionFrame):
            bump_voice_counter("moonshine_final_transcript_count")
            turn = self.turn
            generation = self.controller.current
            if turn is None:
                turn = TurnState(generation.turn_id)
                turn.session_id = generation.session_id
                turn.generation_id = generation.generation_id
                self.turn = turn
            trace_event("turn", "stt_segment_final", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=frame.text, finalized=getattr(frame, "finalized", None))
            if turn.transcript_arrived(frame.text):
                turn.transcript_ready = True
                trace_event("turn", "transcript_buffer_updated", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=turn.text, transcript_segments=len(turn.transcript_segments))
                record = self.turn_records.get(turn.turn_id)
                if record is not None:
                    record["user_segments"] = list(turn.transcript_segments)
                    write_turn_record(record)
                trace_event("moonshine", "moonshine_transcript_final", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=frame.text)
                await self.try_finalize_turn(turn, source="transcript_final")
            return
        await self.push_frame(frame, direction)

    # ------------------------------------------------------------------
    # Sección 3: UNA SOLA FUNCIÓN DE DECISIÓN.
    # Puede llamarse desde: evento SmartTurn (via UserStoppedSpeakingFrame),
    # llegada de transcript, fin de grace window.  Nunca duplicada.
    # ------------------------------------------------------------------
    async def try_finalize_turn(self, turn: TurnState, source: str):
        trace_event("turn", "try_finalize_turn", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=f"source={source} speech_active={turn.speech_active} smart_turn={turn.smart_turn_decision} transcript_ready={turn.transcript_ready} finalized={turn.finalized}")
        if turn.finalized:
            return
        if turn.speech_active:
            return
        if turn.smart_turn_decision != "COMPLETE":
            return
        if not turn.transcript_ready:
            # Sección 5: SmartTurn llegó primero.  NO perdemos la decisión.
            # Estado WAITING_TRANSCRIPT + pequeño watchdog (2.5 s) que reporta
            # STT_TRANSCRIPT_MISSING_AFTER_TURN_COMPLETE, nunca un timeout genérico.
            turn.phase = TurnPhase.WAITING_TRANSCRIPT
            self.turn_state = "WAITING_TRANSCRIPT"
            if self._transcript_watchdog_task is None or self._transcript_watchdog_task.done():
                self._transcript_watchdog_task = asyncio.create_task(self._transcript_watchdog(turn))
            return
        text = turn.text
        if not text:
            return
        delay, policy = completion_guard_delay(text)
        trace_event("turn", "grace_started", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=policy, grace_ms=round(delay * 1000))
        if turn.grace_task is None or turn.grace_task.done():
            turn.grace_task = asyncio.create_task(self._finalize_after_grace(turn, text, delay, source))
            self._grace_task = turn.grace_task
        else:
            # Ya hay una grace programada para este turno; el texto nuevo se
            # consideró al programarla.  Evitamos duplicar.
            trace_event("turn", "grace_already_scheduled", session_id=turn.session_id, turn_id=turn.turn_id, detail=f"source={source}")

    async def _transcript_watchdog(self, turn: TurnState):
        try:
            await asyncio.sleep(TRANSCRIPT_ARRIVAL_WATCHDOG_SECS)
        except asyncio.CancelledError:
            return
        if turn is not self.turn or turn.finalized:
            return
        if not turn.transcript_ready:
            trace_event("turn", "STT_TRANSCRIPT_MISSING_AFTER_TURN_COMPLETE", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", status="error", detail=f"SmartTurn COMPLETE sin transcript final tras {TRANSCRIPT_ARRIVAL_WATCHDOG_SECS}s")
            self.turn_state = "ERROR_STT_MISSING"
            await self._notify_frontend("stt_transcript_missing", {"turn_id": turn.turn_id, "error_code": "STT_TRANSCRIPT_MISSING_AFTER_TURN_COMPLETE"})
        # El watchdog NO cierra el turno: es diagnóstico.  Si el transcript
        # llega después, try_finalize_turn seguirá funcionando.

    async def _finalize_after_grace(self, turn: TurnState, text: str, delay: float, source: str):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if turn is not self.turn or turn.finalized:
            return
        # El buffer puede haber crecido mientras corría la grace (segmento
        # final tardío).  Usamos el texto ACTUAL, no el snapshot del momento
        # en que se programó.
        current_text = turn.text or text
        await self._finalize_turn_now(turn, current_text)

    async def _finalize_turn_now(self, turn: TurnState, text: str):
        if turn.finalized:
            return
        self._cancel_scheduled_tasks("finalize")
        turn.finalized = True
        turn.phase = TurnPhase.FINALIZED
        self.turn_state = "FINALIZED"
        trace_event("turn", "grace_finished", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail="no speech resumed")
        trace_event("turn", "turn_finalized", session_id=turn.session_id, turn_id=turn.turn_id, generation_id=turn.generation_id or "", detail=text, transcript_segments=len(turn.transcript_segments), decision="COMPLETE")
        record = self.turn_records.get(turn.turn_id)
        if record is not None:
            record["user_final_text"] = text
            record["turn_state_history"].extend(["COMPLETE_PENDING", "FINALIZED"])
            write_turn_record(record)
        # Sección 12: recién AHORA (turno finalizado) creamos la nueva
        # assistant generation y despachamos al backend.
        generation = self.controller.continue_turn()
        turn.assistant_generation_id = generation.generation_id
        self._active_assistant_generation_id = generation.generation_id
        CURRENT_TURN_DEBUG.update(session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation.generation_id)
        trace_event("turn", "assistant_generation_created", session_id=generation.session_id, turn_id=turn.turn_id, generation_id=generation.generation_id, detail="created after turn finalized")
        # Invariante C: backend_dispatch_count nunca > 1.
        if turn.backend_dispatched or turn.backend_dispatch_count > 0:
            trace_event("voice", "DUPLICATE_DISPATCH_BLOCKED", session_id=generation.session_id, turn_id=turn.turn_id, generation_id=generation.generation_id, status="error", detail=f"backend_dispatch_count={turn.backend_dispatch_count}")
            return
        turn.backend_dispatched = True
        turn.backend_dispatch_count += 1
        trace_event("voice", "backend_dispatch_started", session_id=generation.session_id, turn_id=turn.turn_id, generation_id=generation.generation_id, detail=text)
        # Sección 9: RETRIEVING recién ahora, con dispatch real al backend.
        await self._notify_frontend("backend_dispatch_started", {"turn_id": turn.turn_id, "generation_id": generation.generation_id, "question": text})
        if _looks_like_web_request(text):
            trace_event("voice", "web_search_started", session_id=generation.session_id, turn_id=turn.turn_id, generation_id=generation.generation_id, detail=text)
            await self._notify_frontend("web_search_started", {"turn_id": turn.turn_id, "generation_id": generation.generation_id})
        task = asyncio.create_task(self._answer(text, generation))
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        self.controller.task = task

    async def _answer(self, text, generation):
        generation_id = generation.generation_id
        started = time.perf_counter()
        trace_event("voice", "backend_request_started", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=text)
        try:
            response = await self.http_client.post("/api/ask-text", json={"question": text, "session_id": generation.session_id, "turn_id": generation.turn_id, "generation_id": generation_id, "source": "human"})
            status = response.status_code
            payload = response.json()
            trace_event("voice", "backend_json_parsed", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=','.join(sorted(payload.keys())))
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            if status >= 400:
                trace_event("voice", "backend_response_received", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, status="error", detail=f"HTTP {status}", elapsed_ms=elapsed)
                raise RuntimeError(payload.get("error_code", f"backend HTTP {status}"))
            trace_event("voice", "backend_response_received", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=f"HTTP {status}", elapsed_ms=elapsed)
            if not self.controller.is_current(generation_id) or payload.get("state") == "INTERRUPTED":
                return
            await self._emit_assistant_answer(text, generation, payload, started)
        except asyncio.CancelledError:
            raise
        except (httpx.ReadTimeout, httpx.ConnectTimeout):
            trace_event("voice", "backend_request_timeout", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, status="error", detail="backend request timeout", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            if self.controller.is_current(generation_id):
                await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
                await self.push_frame(LLMTextFrame("El modelo tardó demasiado en responder. Probá nuevamente."), FrameDirection.DOWNSTREAM)
                await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)
        except Exception as exc:
            trace_event("voice", "backend_request_failed", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, status="error", detail=f"{type(exc).__name__}: {exc}", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            print(traceback.format_exc(), flush=True)
            if self.controller.is_current(generation_id):
                await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
                await self.push_frame(LLMTextFrame("No pude consultar la guía en este momento."), FrameDirection.DOWNSTREAM)
                await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    async def _emit_assistant_answer(self, text, generation, payload, started):
        generation_id = generation.generation_id
        answer = payload.get("answer") or "No pude completar la respuesta."
        response_buffer = AssistantResponseBuffer(generation_id)
        response_buffer.append(answer)
        canonical_answer = response_buffer.finalize()
        answer = canonical_answer
        CURRENT_TTS_TRACE.update(session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, tts_source_text=canonical_answer)
        trace_event("voice", "assistant_response_buffer_finalized", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=f"chars={len(canonical_answer)}", assistant_final_text=canonical_answer)
        record = self.turn_records.get(generation.turn_id)
        if record is not None:
            record["assistant_final_text"] = canonical_answer
            record["timings"]["backend_ms"] = round((time.perf_counter() - started) * 1000, 2)
            write_turn_record(record)
        trace_event("voice", "assistant_answer_extracted", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=f"answer_length={len(answer)}")
        trace_event("voice", "assistant_text_frame_created", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail=answer)
        # RTVI emits bot-llm events from these frames; the old code only sent
        # TTSSpeakFrame, so the UI never left RETRIEVING and no assistant text
        # was visible even when the backend had answered.
        trace_event("voice", "assistant_frame_pushed", session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id, detail="LLMFullResponseStartFrame,LLMTextFrame,LLMFullResponseEndFrame")
        CURRENT_TTS_TRACE.update(session_id=generation.session_id, turn_id=generation.turn_id, generation_id=generation_id)
        await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
        await self.push_frame(LLMTextFrame(answer), FrameDirection.DOWNSTREAM)
        await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)
        # La generación activa termina de emitir; ya no es cancelable por barge-in.
        if self._active_assistant_generation_id == generation_id:
            self._active_assistant_generation_id = None


class TracedMoonshineSTTService(MoonshineSTTService):
    """Keep Moonshine's emitted final frame observable before downstream flow."""

    async def process_generator(self, generator):
        async for frame in generator:
            if frame is not None and type(frame).__name__ == "TranscriptionFrame":
                trace_event("moonshine", "moonshine_transcript_emitted", detail=f"finalized={getattr(frame, 'finalized', None)} text={frame.text}")
            if frame is not None:
                if type(frame).__name__ == "TranscriptionFrame":
                    trace_event("moonshine", "moonshine_push_downstream", detail=f"next={type(getattr(self, '_next', None)).__name__} next_name={getattr(getattr(self, '_next', None), 'name', '')}")
                await self.push_frame(frame)
                if type(frame).__name__ == "TranscriptionFrame":
                    trace_event("moonshine", "moonshine_push_downstream_done")


class TracedPiperTTSService(PiperHttpTTSService):
    def __init__(self, *args, **kwargs):
        sample_rate = kwargs.get("sample_rate")
        super().__init__(*args, **kwargs)
        if sample_rate:
            self._sample_rate = sample_rate

    async def run_tts(self, text: str, context_id: str):
        ids = dict(CURRENT_TTS_TRACE)
        trace_event("tts", "tts_input_received", **ids, detail=f"text_length={len(text)}")
        trace_event("piper", "piper_request_started", **ids, detail=f"text_length={len(text)}")
        started = time.perf_counter()
        audio_started = False
        try:
            async for frame in super().run_tts(text, context_id):
                if isinstance(frame, TTSAudioRawFrame):
                    if not audio_started:
                        audio_started = True
                        trace_event("tts", "tts_audio_received", **ids, detail=f"bytes={len(frame.audio)}", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
                        trace_event("voice", "transport_audio_send_started", **ids)
                yield frame
            if audio_started:
                trace_event("voice", "transport_audio_send_finished", **ids)
            canonical = str(ids.get("tts_source_text", ""))
            # El TTS recibe la respuesta por oraciones; sólo divergen si la oración no está contenida en el texto canónico.
            if canonical and normalized_text(text) not in normalized_text(canonical):
                trace_event("voice", "TEXT_TTS_DIVERGENCE", **ids, status="error", detail="tts sentence not found in canonical assistant text", assistant_final_text=canonical, tts_full_text=text)
            if ids.get("turn_id"):
                session_dir = human_session_dir()
                if session_dir:
                    try:
                        path = session_dir / "turns" / f"{ids['turn_id']}.json"
                        record = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"turn_id": ids["turn_id"]}
                        record.setdefault("tts_segments", []).append(text)
                        record["tts_full_text"] = " ".join(record["tts_segments"])
                        write_turn_record(record)
                    except (OSError, json.JSONDecodeError):
                        pass
            trace_event("piper", "piper_response_received", **ids, detail="audio stream completed", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            trace_event("voice", "turn_finished", **ids, detail="tts/audio complete", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
        except Exception as exc:
            trace_event("piper", "piper_exception", **ids, status="error", detail=f"{type(exc).__name__}: {exc}", elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
            raise


def build_smallwebrtc_pipeline(connection, backend_url=None):
    backend_url = backend_url or os.getenv("BACKEND_URL", "http://localhost:5000")
    transport = SmallWebRTCTransport(connection, TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_in_sample_rate=16000, audio_out_sample_rate=16000, audio_out_channels=1))
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(confidence=0.6, start_secs=0.1, stop_secs=0.6, min_volume=0.2)))
    stt = TracedMoonshineSTTService(settings=TracedMoonshineSTTService.Settings(model=Model.BASE_STREAMING, language=Language.ES))
    smart_turn = TracedSmartTurnAnalyzer(cpu_count=1, params=SmartTurnParams(stop_secs=1.5))
    turn_manager = UserTurnProcessor(user_turn_strategies=UserTurnStrategies(start=[VADUserTurnStartStrategy()], stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=smart_turn, wait_for_transcript=False)]), user_turn_stop_timeout=USER_TURN_STOP_TIMEOUT_SECS)
    rag = GianaRAGProcessor(backend_url=backend_url)
    session = aiohttp.ClientSession()
    piper_url = os.getenv("PIPER_URL", "http://piper:5000/synthesize")
    if not piper_url.rstrip("/").endswith("/synthesize"):
        piper_url = piper_url.rstrip("/") + "/synthesize"
    tts = TracedPiperTTSService(base_url=piper_url, aiohttp_session=session, sample_rate=16000, settings=TracedPiperTTSService.Settings(voice=os.getenv("PIPER_VOICE", "es_AR-daniela-high"), language=Language.ES))
    return transport, Pipeline([transport.input(), vad, stt, turn_manager, rag, tts, transport.output()])


def build_livekit_pipeline(url, token, room_name, backend_url=None):
    backend_url = backend_url or os.getenv("BACKEND_URL", "http://localhost:5000")
    transport = LiveKitTransport(url=url, token=token, room_name=room_name, params=LiveKitParams(audio_in_enabled=True, audio_out_enabled=True, audio_in_sample_rate=16000, audio_out_sample_rate=16000, audio_out_channels=1))
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(confidence=0.6, start_secs=0.1, stop_secs=0.6, min_volume=0.2)))
    stt = TracedMoonshineSTTService(settings=TracedMoonshineSTTService.Settings(model=Model.BASE_STREAMING, language=Language.ES))
    smart_turn = TracedSmartTurnAnalyzer(cpu_count=1, params=SmartTurnParams(stop_secs=1.5))
    turn_manager = UserTurnProcessor(user_turn_strategies=UserTurnStrategies(start=[VADUserTurnStartStrategy()], stop=[TurnAnalyzerUserTurnStopStrategy(turn_analyzer=smart_turn, wait_for_transcript=False)]), user_turn_stop_timeout=USER_TURN_STOP_TIMEOUT_SECS)
    rag = GianaRAGProcessor(backend_url=backend_url)
    session = aiohttp.ClientSession()
    piper_url = os.getenv("PIPER_URL", "http://piper:5000/synthesize")
    if not piper_url.rstrip("/").endswith("/synthesize"):
        piper_url = piper_url.rstrip("/") + "/synthesize"
    tts = TracedPiperTTSService(base_url=piper_url, aiohttp_session=session, sample_rate=16000, settings=TracedPiperTTSService.Settings(voice=os.getenv("PIPER_VOICE", "es_AR-daniela-high"), language=Language.ES))
    return transport, Pipeline([transport.input(), vad, stt, turn_manager, rag, tts, transport.output()])
