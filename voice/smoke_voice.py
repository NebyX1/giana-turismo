import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice.agent import ConversationState, GenerationController


async def main():
    c = GenerationController("smoke")
    first = c.start()
    c.task = asyncio.create_task(asyncio.sleep(10))
    await c.interrupt()
    second = c.start()
    assert first.generation_id != second.generation_id
    assert c.current.state == ConversationState.RETRIEVING
    print("generation cancellation: PASS")


if __name__ == "__main__": asyncio.run(main())
