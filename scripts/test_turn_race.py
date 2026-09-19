"""Race condition tests: SmartTurn vs Moonshine transcript arrival order.

Cubre las secciones 15-18 del brief GIANA TURN RACE FIX:
  - Orden A: SmartTurn COMPLETE antes del transcript (el bug original).
  - Orden B: transcript antes de SmartTurn COMPLETE.
  - Permutaciones de timing: 0/10/50/100/250/500 ms en ambos órdenes.
  - 100 iteraciones por variante: 0 deadlocks, 0 timeouts, 0 dispatches duplicados.

No necesita LLM real: el backend se reemplaza por un servidor HTTP local que
responde JSON fijo.  Sólo se ejercita la state machine del procesador.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipecat.frames.frames import (  # noqa: E402
    InterruptionFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402

from voice.pipeline import GianaRAGProcessor, TurnPhase  # noqa: E402
from voice.trace import TRACE_PATH  # noqa: E402

QUESTION = "¿Vos me podés escuchar?"

# ------------------------------------------------------------------
# Trace capture: sólo leemos las líneas NUEVAS del trace por turno, para no
# mezclar con corridas previas (los turn-ids se repiten entre corridas).
# ------------------------------------------------------------------


class TraceCapture:
    def __init__(self):
        self.offset = 0
        if TRACE_PATH.exists():
            self.offset = TRACE_PATH.stat().st_size

    def snapshot(self):
        if TRACE_PATH.exists():
            self.offset = TRACE_PATH.stat().st_size

    def events(self, turn_id: str) -> list[dict]:
        if not TRACE_PATH.exists():
            return []
        with TRACE_PATH.open("rb") as handle:
            handle.seek(self.offset)
            new_bytes = handle.read()
        events = []
        for line in new_bytes.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("turn_id") == turn_id:
                events.append(item)
        return events

    def event_names(self, turn_id: str) -> list[str]:
        return [item["event"] for item in self.events(turn_id)]


class Harness:
    """Procesador con push_frame capturado y backend HTTP fake."""

    def __init__(self, backend_port: int):
        self.tracer = TraceCapture()
        self.processor = GianaRAGProcessor(backend_url=f"http://127.0.0.1:{backend_port}")
        self.pushed = []
        original_push = self.processor.push_frame

        async def capture(frame, *args, **kwargs):
            self.pushed.append(frame)
            try:
                await original_push(frame, *args, **kwargs)
            except Exception:
                pass

        self.processor.push_frame = capture
        self.backend_dispatches = []
        # Backend fake: responde inmediatamente; registra los requests.
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        harness = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                harness.backend_dispatches.append(body)
                payload = json.dumps({"answer": "Respuesta de prueba.", "state": "ANSWERABLE", "route": "HYBRID_RERANK", "generation_id": body.get("generation_id", "test"), "evidence": []}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", backend_port), Handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    async def aclose(self):
        await self.processor.http_client.aclose()


async def run_turn(h: Harness, order: str, delay_ms: int) -> dict:
    """Ejecuta un user turn sintético con el orden/timing indicado.

    order='A': SmartTurn COMPLETE primero, transcript después.
    order='B': transcript primero, SmartTurn COMPLETE después.
    delay_ms: separación entre los dos eventos (>= 0).
    """
    p = h.processor
    h.tracer.snapshot()
    start_dispatch_index = len(h.backend_dispatches)
    # speech start
    await p.process_frame(VADUserStartedSpeakingFrame(start_secs=0.2), FrameDirection.DOWNSTREAM)
    await p.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    turn_id = p.turn.turn_id if p.turn else "NONE"

    async def smart_turn_complete():
        await p.process_frame(VADUserStoppedSpeakingFrame(stop_secs=0.4), FrameDirection.DOWNSTREAM)
        await p.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    async def transcript_final():
        await p.process_frame(TranscriptionFrame(text=QUESTION, user_id="test", timestamp="0.00", finalized=True), FrameDirection.DOWNSTREAM)

    delay = delay_ms / 1000.0
    if order == "A":
        await smart_turn_complete()
        await asyncio.sleep(delay)
        await transcript_final()
    else:
        await transcript_final()
        await asyncio.sleep(delay)
        await smart_turn_complete()

    # Espera a que corra la grace window + dispatch (grace máx 1.1 s) con
    # margen: nunca usamos timeouts de 25 s; aquí el límite ES el assertion.
    deadline = time.perf_counter() + 3.0
    timed_out = True
    while time.perf_counter() < deadline:
        turn = p.turn
        if turn is not None and turn.finalized and len(h.backend_dispatches) > start_dispatch_index:
            timed_out = False
            break
        await asyncio.sleep(0.01)
    if not timed_out:
        await asyncio.sleep(0.05)  # margen para que el dispatch llegue al fake backend

    turn = p.turn
    events = h.tracer.event_names(turn_id)
    dispatches = [d for d in h.backend_dispatches[start_dispatch_index:] if d.get("turn_id") == turn_id]
    return {
        "turn": turn,
        "turn_id": turn_id,
        "events": events,
        "dispatches": dispatches,
        "timed_out": timed_out,
    }


def expected_sequence_ok(events: list[str]) -> tuple[bool, str]:
    """Sección 23: el trace OBLIGATORIO del fix (los eventos de state machine;
    smart_turn_result sólo existe en runtime real con el analyzer)."""
    must_have = ["turn_started", "complete_pending", "try_finalize_turn", "turn_finalized", "backend_dispatch_started"]
    for name in must_have:
        if name not in events:
            return False, f"missing event: {name}"
    return True, ""


def check_turn_invariants(turn, dispatches, order: str, delay_ms: int) -> list[str]:
    errors = []
    label = f"{order} delay={delay_ms}ms turn={turn.turn_id if turn else 'NONE'}"
    if turn is None:
        errors.append(f"{label}: no turn object")
        return errors
    # Invariante A: COMPLETE + transcript_ready + !speech_active -> finalized
    if turn.smart_turn_decision == "COMPLETE" and turn.transcript_ready and not turn.speech_active:
        if not turn.finalized:
            errors.append(f"{label}: invariante A violada: condiciones cumplidas pero turno NO finalizado")
    # Invariante B/C: finalized -> exactamente 1 dispatch
    if turn.finalized:
        if len(dispatches) != 1:
            errors.append(f"{label}: invariante B/C violada: finalized con {len(dispatches)} dispatches (esperado 1)")
        if turn.backend_dispatch_count != 1:
            errors.append(f"{label}: backend_dispatch_count={turn.backend_dispatch_count} (esperado 1)")
        if turn.text != QUESTION:
            errors.append(f"{label}: texto final difiere: {turn.text!r}")
    if turn.phase != TurnPhase.FINALIZED and turn.finalized:
        errors.append(f"{label}: fase inconsistente")
    return errors


async def run_generation_lifecycle_test(h: Harness) -> tuple[str, list[str]]:
    """Secciones 11-13: un user turn NUEVO no debe cancelar su propia
    generación assistant; el barge-in cancela SOLO la generación activa
    ANTERIOR (si existe)."""
    errors = []
    p = h.processor
    h.tracer.snapshot()

    # Turno 1 completo (crea generación assistant activa tras finalizar).
    await p.process_frame(VADUserStartedSpeakingFrame(start_secs=0.2), FrameDirection.DOWNSTREAM)
    await p.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await p.process_frame(VADUserStoppedSpeakingFrame(stop_secs=0.4), FrameDirection.DOWNSTREAM)
    await p.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await p.process_frame(TranscriptionFrame(text="primera pregunta", user_id="test", timestamp="0.00", finalized=True), FrameDirection.DOWNSTREAM)
    deadline = time.perf_counter() + 3.0
    while time.perf_counter() < deadline:
        turn = p.turn
        if turn is not None and turn.finalized and turn.assistant_generation_id:
            break
        await asyncio.sleep(0.01)
    turn1 = p.turn
    if turn1 is None or not turn1.finalized or not turn1.assistant_generation_id:
        return "FAIL", ["generation lifecycle: turno 1 no finalizó sin assistant generation"]
    gen1 = turn1.assistant_generation_id
    # Turno 2: el usuario interrumpe (barge-in) mientras la generación del
    # turno 1 sigue activa.
    await p.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    await p.process_frame(VADUserStartedSpeakingFrame(start_secs=0.2), FrameDirection.DOWNSTREAM)
    await p.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    turn2 = p.turn
    if turn2 is None:
        return "FAIL", ["generation lifecycle: turno 2 no se creó"]
    # Invariante sección 12: el turno nuevo NO creó su generación assistant
    # todavía (se crea al finalizar).
    if turn2.assistant_generation_id is not None:
        errors.append(f"generation lifecycle: turno 2 creó generation {turn2.assistant_generation_id} antes de finalizar (esperado None)")
    # El barge-in canceló la generación activa del turno 1 (registrada).
    cancelled = [e for e in h.tracer.events(turn2.turn_id) + h.tracer.events(turn1.turn_id) if e["event"] == "generation_cancelled"]
    if not any(e.get("generation_id") == gen1 for e in cancelled):
        errors.append(f"generation lifecycle: barge-in no canceló la generación activa {gen1}")
    # El turno 2 nunca canceló SU PROPIA generation_id del user turn.
    self_cancel = [e for e in cancelled if e.get("generation_id") == turn2.generation_id]
    if self_cancel:
        errors.append(f"generation lifecycle: turno 2 canceló su propia generación ({turn2.generation_id})")
    # Completamos el turno 2.
    await p.process_frame(VADUserStoppedSpeakingFrame(stop_secs=0.4), FrameDirection.DOWNSTREAM)
    await p.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await p.process_frame(TranscriptionFrame(text="segunda pregunta", user_id="test", timestamp="0.00", finalized=True), FrameDirection.DOWNSTREAM)
    deadline = time.perf_counter() + 3.0
    while time.perf_counter() < deadline:
        turn2 = p.turn
        if turn2 is not None and turn2.finalized and turn2.backend_dispatched:
            break
        await asyncio.sleep(0.01)
    turn2 = p.turn
    if turn2 is None or not turn2.finalized:
        errors.append("generation lifecycle: turno 2 no finalizó tras transcript")
    elif turn2.assistant_generation_id == gen1:
        errors.append("generation lifecycle: turno 2 reutilizó la generación del turno 1")
    return ("PASS" if not errors else "FAIL"), errors


async def run_stop_timeout_test(h: Harness) -> tuple[str, list[str]]:
    """SmartTurn INCOMPLETE + UserStoppedSpeakingFrame por stop-timeout con
    transcript final: el turno DEBE finalizar y despachar (bug: turn_kept_open)."""
    from voice.pipeline import LAST_SMART_TURN_DECISION

    p = h.processor
    h.tracer.snapshot()
    start_dispatch_index = len(h.backend_dispatches)
    LAST_SMART_TURN_DECISION["decision"] = "INCOMPLETE"
    try:
        await p.process_frame(VADUserStartedSpeakingFrame(start_secs=0.2), FrameDirection.DOWNSTREAM)
        await p.process_frame(UserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        turn_id = p.turn.turn_id
        await p.process_frame(TranscriptionFrame(text=QUESTION, user_id="test", timestamp="0.00", finalized=True), FrameDirection.DOWNSTREAM)
        await p.process_frame(VADUserStoppedSpeakingFrame(stop_secs=0.4), FrameDirection.DOWNSTREAM)
        await p.process_frame(UserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        deadline = time.perf_counter() + 3.0
        while time.perf_counter() < deadline:
            if p.turn is not None and p.turn.finalized and len(h.backend_dispatches) > start_dispatch_index:
                break
            await asyncio.sleep(0.01)
    finally:
        LAST_SMART_TURN_DECISION["decision"] = ""
    dispatches = [d for d in h.backend_dispatches[start_dispatch_index:] if d.get("turn_id") == turn_id]
    errors = []
    if p.turn is None or not p.turn.finalized:
        errors.append("stop timeout: turno con transcript quedó abierto tras UserStoppedSpeakingFrame INCOMPLETE")
    if len(dispatches) != 1:
        errors.append(f"stop timeout: {len(dispatches)} dispatches (esperado 1)")
    return ("PASS" if not errors else "FAIL"), errors


async def main():
    global_failures = []
    summary = {"orderA": "PASS", "orderB": "PASS", "permutations": "PASS", "stress": "PASS", "duplicate": "0"}
    total_dispatches = 0
    duplicate_total = 0

    h = Harness(backend_port=18123)

    # ------------------------------------------------------------------
    # Orden A (sección 15): SmartTurn COMPLETE primero, transcript después.
    # ------------------------------------------------------------------
    resultA = await run_turn(h, "A", 200)
    errorsA = check_turn_invariants(resultA["turn"], resultA["dispatches"], "A", 200)
    seq_ok, seq_err = expected_sequence_ok(resultA["events"])
    if not seq_ok:
        errorsA.append(f"Order A secuencia: {seq_err}")
    if errorsA or resultA["timed_out"]:
        summary["orderA"] = "FAIL"
        global_failures.extend(errorsA)
        if resultA["timed_out"]:
            global_failures.append("Order A: TIMEOUT (turno no finalizado)")
    total_dispatches += len(resultA["dispatches"])
    if resultA["turn"] is not None and resultA["turn"].backend_dispatch_count > 1:
        duplicate_total += 1

    # ------------------------------------------------------------------
    # Orden B (sección 16): transcript primero, SmartTurn después.
    # ------------------------------------------------------------------
    resultB = await run_turn(h, "B", 200)
    errorsB = check_turn_invariants(resultB["turn"], resultB["dispatches"], "B", 200)
    seq_ok, seq_err = expected_sequence_ok(resultB["events"])
    if not seq_ok:
        errorsB.append(f"Order B secuencia: {seq_err}")
    if errorsB or resultB["timed_out"]:
        summary["orderB"] = "FAIL"
        global_failures.extend(errorsB)
        if resultB["timed_out"]:
            global_failures.append("Order B: TIMEOUT (turno no finalizado)")
    total_dispatches += len(resultB["dispatches"])
    if resultB["turn"] is not None and resultB["turn"].backend_dispatch_count > 1:
        duplicate_total += 1

    # ------------------------------------------------------------------
    # Timing permutations (sección 17): 0/10/50/100/250/500 ms, ambos órdenes.
    # ------------------------------------------------------------------
    for order in ("A", "B"):
        for delay_ms in (0, 10, 50, 100, 250, 500):
            result = await run_turn(h, order, delay_ms)
            errors = check_turn_invariants(result["turn"], result["dispatches"], order, delay_ms)
            if result["timed_out"]:
                errors.append(f"permutation {order}/{delay_ms}ms: TIMEOUT")
            if errors:
                summary["permutations"] = "FAIL"
                global_failures.extend(errors)
            total_dispatches += len(result["dispatches"])
            if result["turn"] is not None and result["turn"].backend_dispatch_count > 1:
                duplicate_total += 1

    # ------------------------------------------------------------------
    # 100x stress por variante (sección 18): sin deadlocks/timeouts/duplicados.
    # ------------------------------------------------------------------
    variants = [("A", 0), ("B", 0), ("A", 50), ("B", 50)]
    for order, delay_ms in variants:
        for iteration in range(100):
            result = await run_turn(h, order, delay_ms)
            errors = check_turn_invariants(result["turn"], result["dispatches"], f"{order}x100", delay_ms)
            if result["timed_out"]:
                errors.append(f"stress {order}/{delay_ms} iter={iteration}: TIMEOUT")
            if errors:
                summary["stress"] = "FAIL"
                global_failures.extend(errors[:3])
            total_dispatches += len(result["dispatches"])
            if result["turn"] is not None and result["turn"].backend_dispatch_count > 1:
                duplicate_total += 1
    summary["duplicate"] = f"0/{total_dispatches}" if duplicate_total == 0 else f"{duplicate_total}/{total_dispatches}"
    if duplicate_total:
        global_failures.append(f"dispatches duplicados detectados: {duplicate_total}")

    # ------------------------------------------------------------------
    # Generation lifecycle (secciones 11-13).
    # ------------------------------------------------------------------
    summary["lifecycle"], lifecycle_errors = await run_generation_lifecycle_test(h)
    if lifecycle_errors:
        global_failures.extend(lifecycle_errors)

    summary["stop_timeout"], stop_timeout_errors = await run_stop_timeout_test(Harness(backend_port=18124))
    if stop_timeout_errors:
        global_failures.extend(stop_timeout_errors)

    await h.aclose()

    print(f"Order A: {summary['orderA']}")
    print(f"Order B: {summary['orderB']}")
    print(f"Timing permutations: {summary['permutations']}")
    print(f"100x stress: {summary['stress']}")
    print(f"Duplicate dispatch: {summary['duplicate']}")
    print(f"Generation lifecycle: {summary['lifecycle']}")
    print(f"Stop timeout (INCOMPLETE): {summary['stop_timeout']}")
    if global_failures:
        print(f"\nFAILURES ({len(global_failures)}):")
        for failure in global_failures[:20]:
            print(f"  - {failure}")
        print("RACE_TEST_FAIL")
        sys.exit(1)
    print("RACE_TEST_PASS")


if __name__ == "__main__":
    asyncio.run(main())