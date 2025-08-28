from fastapi import Request

from ..core.client import SolanaClient

def get_solana_client(request: Request) -> SolanaClient:
    """Safe FastAPI dependency to extract SolanaClient from app state."""
    return request.app.state.solana