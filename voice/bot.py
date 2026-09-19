"""Pipecat runner entrypoint: SmallWebRTC first, LiveKit selectable at the end."""
import asyncio
import traceback
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.runner.run import main as runner_main
from pipecat.runner.types import LiveKitRunnerArguments, RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.frames.frames import TTSSpeakFrame

from voice.pipeline import build_livekit_pipeline, build_smallwebrtc_pipeline
from voice.trace import trace_event


async def bot(runner_args: RunnerArguments):
    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        transport, pipeline = build_smallwebrtc_pipeline(runner_args.webrtc_connection)
    elif isinstance(runner_args, LiveKitRunnerArguments):
        transport, pipeline = build_livekit_pipeline(runner_args.url, runner_args.token, runner_args.room_name)
    else:
        raise RuntimeError(f"transporte no soportado: {type(runner_args).__name__}")
    # idle_timeout_secs=None: el pipeline NO se cancela por inactividad.
    # En una sesión de voz humana el usuario puede quedarse callado más de
    # 5 minutos antes de hablar; matar el pipeline por idle rompe la sesión
    # (observado: "Idle timeout detected" a los 300 s).
    task = PipelineTask(pipeline, idle_timeout_secs=None, params=PipelineParams(allow_interruptions=True, enable_metrics=True, enable_usage_metrics=False))

    async def welcome():
        await asyncio.sleep(0.35)
        trace_event("voice", "welcome_tts_started", session_id="voice", detail="fixed welcome")
        await task.queue_frame(TTSSpeakFrame(text="Hola, soy Giana, la asistente turística de Lavalleja. ¿En qué te puedo ayudar?", append_to_context=False))
        trace_event("voice", "welcome_tts_finished", session_id="voice")

    welcome_task = asyncio.create_task(welcome())
    def welcome_done(done):
        if not done.cancelled() and done.exception():
            print(traceback.format_exc(), flush=True)
            trace_event("voice", "welcome_tts_failed", session_id="voice", status="error", detail=str(done.exception()))
    welcome_task.add_done_callback(welcome_done)
    await PipelineRunner().run(task)


if __name__ == "__main__":
    runner_main()
