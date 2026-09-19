"""Conversation state and cancellation primitives shared by both transports."""
import asyncio
import uuid
from dataclasses import dataclass
from enum import StrEnum


class ConversationState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    RETRIEVING = "RETRIEVING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


@dataclass
class Generation:
    session_id: str
    turn_id: str
    generation_id: str
    state: ConversationState = ConversationState.IDLE


class GenerationController:
    def __init__(self, session_id: str):
        self._turn_number = 0
        self.current = Generation(session_id, "turn-0000", str(uuid.uuid4()))
        self.task: asyncio.Task | None = None

    def start(self) -> Generation:
        self._turn_number += 1
        self.current = Generation(self.current.session_id, f"turn-{self._turn_number:04d}", str(uuid.uuid4()), ConversationState.RETRIEVING)
        return self.current

    def continue_turn(self) -> Generation:
        """Invalidate a pending generation while keeping the same semantic turn."""
        self.current = Generation(self.current.session_id, self.current.turn_id, str(uuid.uuid4()), ConversationState.RETRIEVING)
        self.task = None
        return self.current

    def is_current(self, generation_id: str) -> bool:
        return self.current.generation_id == generation_id

    async def interrupt(self):
        if self.task and not self.task.done():
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
        self.current.state = ConversationState.INTERRUPTED
