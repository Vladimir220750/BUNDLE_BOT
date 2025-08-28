from fastapi import Request

from ..core.wallet_manager import WalletManager

def get_wm(request: Request) -> WalletManager:
    """Safe FastAPI dependency to extract SolanaClient from app state."""
    return request.app.state.wm