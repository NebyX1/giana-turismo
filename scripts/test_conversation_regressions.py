"""Exercise real processor queues; a fake backend isolates turn scheduling."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice.runtime import prepare_text_runtime
from voice.pipeline import GianaRAGProcessor, completion_guard_delay
from pipecat.frames.frames import TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame, InterruptionFrame
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.pipeline.runner import PipelineRunner
import httpx


class Sink(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.events = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, RTVIServerMessageFrame):
            self.events.append(frame.data)
        await self.push_frame(frame, direction)


class Regressions(unittest.IsolatedAsyncioTestCase):
    def test_stt_punctuation_cannot_complete_unfinished_clause(self):
        for text in ['Quiero saber dónde podemos', 'Quiero ir al parque y', 'Me gustaría', 'Un lugar donde']:
            for punctuation in ['', '.', '?', '!']:
                with self.subTest(text=text, punctuation=punctuation):
                    self.assertEqual(completion_guard_delay(text+punctuation), (1.1, 'long_or_incomplete_cue'))
        self.assertEqual(completion_guard_delay('¿Qué hora es?'), (0.3, 'short_complete'))

    async def test_multisentence_tokenizer(self):
        prepare_text_runtime()
        from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator
        for _ in range(10):
            aggregator = SimpleTextAggregator()
            parts = [x.text async for x in aggregator.aggregate('Hola. Soy Giana. ¿Seguimos?')]
            tail = await aggregator.flush()
            if tail:
                parts.append(tail.text)
            self.assertEqual(' '.join(parts), 'Hola. Soy Giana. ¿Seguimos?')

    async def test_ten_turns_and_resumed_speech(self):
        rag, sink = GianaRAGProcessor(), Sink()
        calls = []
        async def reply(request):
            import json
            data = json.loads(request.content)
            calls.append(data)
            return httpx.Response(200, json={'answer': 'Una respuesta completa. Con segunda oración.', 'state': 'ANSWERABLE'})
        await rag.http_client.aclose()
        rag.http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url='http://test')
        task = PipelineTask(Pipeline([rag, sink]), params=PipelineParams(), enable_rtvi=False, idle_timeout_secs=None)
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        try:
            for index in range(10):
                await task.queue_frames([UserStartedSpeakingFrame(), TranscriptionFrame(f'Pregunta {index},', 'test', ''), UserStoppedSpeakingFrame()])
                await asyncio.sleep(0.08)
                # Interruption precedes speech start in real transports.
                await task.queue_frames([InterruptionFrame(), UserStartedSpeakingFrame(), TranscriptionFrame('con una continuación.', 'test', ''), UserStoppedSpeakingFrame()])
                async with asyncio.timeout(4):
                    while len([x for x in sink.events if x['event'] == 'assistant_response_finalized']) <= index:
                        await asyncio.sleep(0.02)
                self.assertEqual(calls[index]['question'], f'Pregunta {index}, con una continuación.')
                self.assertEqual(len(calls), index + 1)
            users = [x for x in sink.events if x['event'] == 'user_turn_finalized']
            self.assertEqual(len(users), 10)
            self.assertEqual(len({x['turn_id'] for x in users}), 10)
        finally:
            await task.cancel()
            await runner
            await rag.http_client.aclose()

    async def test_resumed_speech_waits_for_its_own_late_transcript(self):
        rag, sink = GianaRAGProcessor(), Sink()
        calls = []
        async def reply(request):
            import json
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={'answer':'Respuesta a la consulta completa.'})
        await rag.http_client.aclose()
        rag.http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply))
        task = PipelineTask(Pipeline([rag,sink]),enable_rtvi=False,idle_timeout_secs=None)
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        try:
            await task.queue_frames([UserStartedSpeakingFrame(),TranscriptionFrame('Hola, ¿me recibís bien?','test',''),UserStoppedSpeakingFrame()])
            async with asyncio.timeout(3):
                while not (rag.turn and rag.turn.transcript_ready and rag.turn.grace_task):
                    await asyncio.sleep(0.005)
            await task.queue_frames([InterruptionFrame(),UserStartedSpeakingFrame()])
            async with asyncio.timeout(3):
                while not (rag.turn.speech_active and not rag.turn.transcript_ready):
                    await asyncio.sleep(0.005)
            await task.queue_frames([UserStoppedSpeakingFrame()])
            # Longer than the short greeting's 300 ms grace: old code dispatched
            # the greeting alone before Whisper finished the resumed segment.
            await asyncio.sleep(0.8)
            self.assertEqual(calls,[])
            await task.queue_frames([TranscriptionFrame('Quiero comer asado en Minas.','test','')])
            async with asyncio.timeout(4):
                while not calls: await asyncio.sleep(0.02)
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['question'],'Hola, ¿me recibís bien? Quiero comer asado en Minas.')
        finally:
            await task.cancel(); await runner

    async def test_errors_are_visible_and_next_turn_recovers(self):
        rag, sink = GianaRAGProcessor(), Sink()
        count = 0
        async def reply(request):
            nonlocal count
            count += 1
            if count == 1:
                raise httpx.ReadTimeout('controlled timeout', request=request)
            if count == 2:
                return httpx.Response(503, json={'error_code': 'controlled unavailable'})
            return httpx.Response(200, json={'answer': 'Ya puedo responder de nuevo.'})
        await rag.http_client.aclose()
        rag.http_client = httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url='http://test')
        task = PipelineTask(Pipeline([rag, sink]), enable_rtvi=False, idle_timeout_secs=None)
        runner = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
        try:
            for index, expected in enumerate(['El modelo tardó', 'Tuve un problema técnico', 'Ya puedo responder']):
                await task.queue_frames([UserStartedSpeakingFrame(), TranscriptionFrame('Hola Giana.', 'test', ''), UserStoppedSpeakingFrame()])
                async with asyncio.timeout(4):
                    while len([x for x in sink.events if x['event'] == 'assistant_response_finalized']) <= index:
                        await asyncio.sleep(0.02)
                answers = [x for x in sink.events if x['event'] == 'assistant_response_finalized']
                self.assertTrue(answers[-1]['text'].startswith(expected))
        finally:
            await task.cancel()
            await runner
        self.assertTrue(rag.http_client.is_closed)
        self.assertFalse(rag._tasks)


if __name__ == '__main__':
    unittest.main()
