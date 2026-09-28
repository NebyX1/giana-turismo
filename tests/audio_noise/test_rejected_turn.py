import asyncio
import unittest
from unittest.mock import Mock

from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import InterruptionFrame, TranscriptionFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager

from voice.input_quality import STTRejectedFrame
from voice.pipeline import GianaRAGProcessor, TurnPhase


class RejectedTurnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.processor = GianaRAGProcessor(backend_url='http://127.0.0.1:1')
        await self.processor.setup(FrameProcessorSetup(clock=SystemClock(), task_manager=TaskManager(), pipeline_worker=Mock()))
        self.events = []
        async def capture(event, payload): self.events.append(event)
        self.processor._notify_frontend = capture

    async def asyncTearDown(self):
        await self.processor.cleanup()

    async def send(self, frame):
        await self.processor.process_frame(frame, FrameDirection.DOWNSTREAM)

    async def test_rejection_after_stop_suppresses_watchdog_and_backend(self):
        await self.send(UserStartedSpeakingFrame())
        await self.send(UserStoppedSpeakingFrame())
        await self.send(STTRejectedFrame(reason='vad_no_speech'))
        self.assertEqual(self.processor.turn.phase, TurnPhase.REJECTED)
        self.assertFalse(self.processor.turn.backend_dispatched)
        self.assertEqual(self.processor.turn_state, 'LISTENING')
        self.assertIn('voice_input_rejected', self.events)
        self.assertNotIn('stt_transcript_missing', self.events)
        self.assertTrue(self.processor._transcript_watchdog_task is None)

    async def test_rejection_before_stop_is_normal(self):
        await self.send(UserStartedSpeakingFrame())
        await self.send(STTRejectedFrame(reason='impulsive_audio'))
        await self.send(UserStoppedSpeakingFrame())
        self.assertEqual(self.processor.turn.phase, TurnPhase.REJECTED)
        self.assertFalse(self.processor.turn.backend_dispatched)

    async def test_rejected_residual_does_not_erase_real_transcript(self):
        await self.send(UserStartedSpeakingFrame())
        await self.send(TranscriptionFrame(text='Minas', user_id='test', timestamp='0'))
        await self.send(STTRejectedFrame(reason='vad_no_speech'))
        self.assertEqual(self.processor.turn.text, 'Minas')
        self.assertFalse(self.processor.turn.input_rejected)

    async def test_rejected_noise_restores_assistant_answer_instead_of_losing_it(self):
        previous = self.processor.controller.current
        self.processor._active_assistant_generation_id = previous.generation_id
        assistant_task = asyncio.create_task(asyncio.sleep(30))
        self.processor.controller.task = assistant_task

        await self.send(UserStartedSpeakingFrame())
        await self.send(InterruptionFrame())
        self.assertFalse(assistant_task.cancelled())
        await self.send(UserStoppedSpeakingFrame())
        await self.send(STTRejectedFrame(reason='vad_no_speech'))

        self.assertEqual(self.processor.turn.phase, TurnPhase.REJECTED)
        self.assertEqual(self.processor.controller.current.generation_id, previous.generation_id)
        self.assertEqual(self.processor._active_assistant_generation_id, previous.generation_id)
        self.assertFalse(assistant_task.cancelled())

    async def test_accepted_transcript_commits_barge_in_cancellation(self):
        previous = self.processor.controller.current
        self.processor._active_assistant_generation_id = previous.generation_id
        assistant_task = asyncio.create_task(asyncio.sleep(30))
        self.processor.controller.task = assistant_task

        await self.send(UserStartedSpeakingFrame())
        await self.send(InterruptionFrame())
        self.assertFalse(assistant_task.cancelled())
        await self.send(TranscriptionFrame(text='Qué hay para visitar en Minas?', user_id='test', timestamp='0'))

        self.assertTrue(assistant_task.cancelled())
        self.assertIsNone(self.processor._active_assistant_generation_id)
        self.assertIsNone(self.processor._pending_assistant_interruption)

    async def test_answer_ready_during_noise_is_replayed_after_rejection(self):
        previous = self.processor.controller.current
        self.processor._active_assistant_generation_id = previous.generation_id
        await self.send(UserStartedSpeakingFrame())
        await self.send(InterruptionFrame())
        completed = asyncio.Event()

        async def capture_answer(*args, **kwargs):
            completed.set()

        self.processor._emit_assistant_answer = capture_answer
        self.processor._deferred_assistant_answer = (
            'consulta original', previous, {'answer': 'Respuesta recuperada'}, 0.0,
        )
        await self.send(UserStoppedSpeakingFrame())
        await self.send(STTRejectedFrame(reason='vad_no_speech'))

        await asyncio.wait_for(completed.wait(), timeout=1.0)
        self.assertEqual(self.processor._active_assistant_generation_id, previous.generation_id)
        self.assertIsNone(self.processor._deferred_assistant_answer)


if __name__ == '__main__': unittest.main()
