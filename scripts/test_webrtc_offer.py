"""Real signaling gate using aiortc: no human mic claim, but full offer/answer/ICE."""
import asyncio
import json
import time
from fractions import Fraction

import aiohttp
from av import AudioFrame
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack


class SilenceTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.samples = 0

    async def recv(self):
        frame = AudioFrame(format="s16", layout="mono", samples=960)
        frame.planes[0].update(bytes(1920))
        frame.sample_rate = 48000
        frame.pts = self.samples
        frame.time_base = Fraction(1, 48000)
        self.samples += 960
        await asyncio.sleep(0.02)
        return frame


async def main():
    base = "http://127.0.0.1:7860"
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{base}/start", json={"transport": "webrtc", "enableDefaultIceServers": True}) as response:
            response.raise_for_status()
            start = await response.json()
    session_id = start["sessionId"]
    offer_url = f"{base}/sessions/{session_id}/api/offer"
    pc = RTCPeerConnection()
    audio = pc.addTransceiver("audio", direction="sendrecv")
    audio.sender.replaceTrack(SilenceTrack())
    pc.addTransceiver("video", direction="sendrecv")
    pc.createDataChannel("chat", ordered=True)
    states = []
    connected = asyncio.Event()

    @pc.on("iceconnectionstatechange")
    async def on_ice():
        states.append(f"ice={pc.iceConnectionState}")
        if pc.iceConnectionState in {"connected", "completed"}:
            connected.set()

    @pc.on("connectionstatechange")
    async def on_connection():
        states.append(f"pc={pc.connectionState}")
        if pc.connectionState == "connected":
            connected.set()

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    deadline = time.monotonic() + 5
    while pc.iceGatheringState != "complete" and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    payload = {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type, "pc_id": None, "restart_pc": False}
    async with aiohttp.ClientSession() as http:
        async with http.post(offer_url, json=payload) as response:
            status = response.status
            answer = await response.json()
    if status != 200:
        raise RuntimeError(f"offer HTTP {status}: {answer}")
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))
    try:
        await asyncio.wait_for(connected.wait(), timeout=10)
        await asyncio.sleep(2)
    finally:
        await pc.close()
    print(json.dumps({"start_http": 200, "offer_http": status, "session_id": session_id, "audio_track": "sent_silence", "ice": states, "peer_connection": "connected"}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
