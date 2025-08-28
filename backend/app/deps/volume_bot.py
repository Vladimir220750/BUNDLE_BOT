from fastapi import Request

from ..core.volume_bot import VolumeBot

def get_volume_bot(connection: Request) -> VolumeBot:
    """Safe FastAPI dependency to extract SolanaClient from app state."""
    return connection.app.state.volume_bot