import contextlib

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Depends

from .core.config import settings
from .core.data_collector import DataCollector
from .core.volume_bot import VolumeBot
from .core.wallet_manager import WalletManager

from .routes.api import router
from .routes.ws import ws
from .core.client import SolanaClient

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    helius_client = SolanaClient(settings.helius_rpc_url, max_calls=50)
    shift_client = SolanaClient(settings.shift_rpc_url, max_calls=95)

    wm = WalletManager(solana_client=helius_client)
    dc = DataCollector(solana_client=shift_client, wm=wm)
    volume_bot: VolumeBot | None = None

    await dc.start()

    app.state.solana = helius_client
    app.state.dc = dc
    app.state.wm = wm
    app.state.volume_bot = volume_bot

    yield

    await dc.stop()
    await shift_client.close()
    await helius_client.close()

app = FastAPI(
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(ws)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
