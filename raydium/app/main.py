import contextlib

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from .core.config import settings
from .core.client import SolanaClient
from .core.dc import DataCollector
from .routers.ws import ws
from .routers.api import router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    helius_client = SolanaClient(settings.helius_rpc_url)
    dc = DataCollector(solana_client=helius_client)

    app.state.dc = dc
    app.state.solana = helius_client

    yield

    await helius_client.close()

app = FastAPI(
    lifespan=lifespan,
)

app.include_router(ws)
app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
