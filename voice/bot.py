"""Pipecat runner entrypoint: SmallWebRTC first, LiveKit selectable at the end."""
from voice.runtime import prepare_text_runtime

# Fail before /start becomes available, rather than killing TTS and the RTVI
# observer on the first multi-sentence response.
prepare_text_runtime()
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.runner.run import main as runner_main
from pipecat.runner.types import LiveKitRunnerArguments, RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.frames.frames import TTSSpeakFrame

from voice.pipeline import build_livekit_pipeline, build_smallwebrtc_pipeline
from voice.trace import trace_event


async def bot(runner_args: RunnerArguments):
    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        body=runner_args.body if isinstance(runner_args.body,dict) else {}
        conversation_id=body.get('conversation_id')
        if not isinstance(conversation_id,str) or not 1<=len(conversation_id)<=128:
            conversation_id=None
        transport, pipeline = build_smallwebrtc_pipeline(runner_args.webrtc_connection, conversation_id=conversation_id)
    elif isinstance(runner_args, LiveKitRunnerArguments):
        transport, pipeline = build_livekit_pipeline(runner_args.url, runner_args.token, runner_args.room_name)
    else:
        raise RuntimeError(f"transporte no soportado: {type(runner_args).__name__}")
    # idle_timeout_secs=None: el pipeline NO se cancela por inactividad.
    # En una sesión de voz humana el usuario puede quedarse callado más de
    # 5 minutos antes de hablar; matar el pipeline por idle rompe la sesión
    # (observado: "Idle timeout detected" a los 300 s).
    task = PipelineTask(pipeline, idle_timeout_secs=None, params=PipelineParams(allow_interruptions=True, enable_metrics=True, enable_usage_metrics=False))

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        trace_event("voice", "client_disconnected", detail="closing pipeline and session resources")
        await task.cancel()

    welcome_sent = False

    @task.rtvi.event_handler("on_client_ready")
    async def welcome(rtvi):
        nonlocal welcome_sent
        if welcome_sent:
            return
        welcome_sent = True
        trace_event("voice", "welcome_tts_started", session_id="voice", detail="fixed welcome")
        await task.queue_frame(TTSSpeakFrame(text="Hola, soy Gianna, la asistente turística de Lavalleja. ¿En qué te puedo ayudar?", append_to_context=False))
        trace_event("voice", "welcome_tts_queued", session_id="voice")

    await PipelineRunner().run(task)


if __name__ == "__main__":
    runner_main()
