"""Local LiveKit handshake smoke; never prints credentials."""
import asyncio
import os
from pathlib import Path

import yaml


CONFIG = Path(os.getenv("LIVEKIT_CONFIG", "/home/usuario/Documentos/Proyectos IA/Gianna-Alt/livekit.yaml"))


async def main():
    if not CONFIG.exists():
        print("LiveKit config: SKIP (no local config path)")
        return
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    keys = config.get("keys", {})
    if not keys:
        print("LiveKit config: SKIP (no keys)")
        return
    api_key, api_secret = next(iter(keys.items()))
    os.environ["LIVEKIT_API_KEY"] = str(api_key)
    os.environ["LIVEKIT_API_SECRET"] = str(api_secret)
    os.environ["LIVEKIT_URL"] = "ws://127.0.0.1:7880"
    from livekit.api import AccessToken, VideoGrants
    from livekit import rtc
    token = AccessToken(api_key, api_secret).with_identity("giana-smoke").with_grants(VideoGrants(room_join=True, room="giana-smoke")).to_jwt()
    room = rtc.Room()
    await room.connect("ws://127.0.0.1:7880", token)
    print("LiveKit handshake: PASS")
    await room.disconnect()


if __name__ == "__main__": asyncio.run(main())
