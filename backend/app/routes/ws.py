import asyncio
from sys import prefix

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from ..core.data_collector import DataCollector
from ..deps.data_collector import get_dc_ws
from ..deps.network import is_allowed_host

ws = APIRouter()

@ws.websocket("/data/")
async def data_ws(
    websocket: WebSocket,
    dc: DataCollector = Depends(get_dc_ws)
):
    host = websocket.headers.get("host")
    if not is_allowed_host(host):
        print(f"Host disallow: {host=}")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    queue = await dc.subscribe()
    while True:
        try:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
            if isinstance(msg, dict):
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg.get("type") == "command":
                    await dc.handle_command(msg.get("command"))

        except asyncio.TimeoutError:
            pass
        except WebSocketDisconnect:
            break

        while not queue.empty():
            data = queue.get_nowait()
            await websocket.send_json({
                "type": "update",
                "payload": data
            })
