import asyncio
from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Depends

from ..deps.dc import get_dc_ws
from ..core.dc import DataCollector

ws = APIRouter()

@ws.websocket("/data/")
async def data_ws(
    websocket: WebSocket,
    dc: DataCollector = Depends(get_dc_ws)
):
    await websocket.accept()
    queue = await dc.subscribe()

    while True:
        try:
            msg = await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
        except asyncio.TimeoutError:
            pass
        except WebSocketDisconnect:
            break

        while not queue.empty():
            update = queue.get_nowait()
            await websocket.send_json(update)
