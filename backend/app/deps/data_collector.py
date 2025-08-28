from fastapi import Request, WebSocket

from ..core.data_collector import DataCollector

def get_dc(connection: Request) -> DataCollector:
    """Safe FastAPI dependency to extract SolanaClient from app state."""
    return connection.app.state.dc

def get_dc_ws(connection: WebSocket) -> DataCollector:
    """Safe FastAPI dependency to extract SolanaClient from app state."""
    return connection.app.state.dc