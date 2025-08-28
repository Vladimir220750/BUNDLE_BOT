import json

from solders.keypair import Keypair

from ..core.config import settings

def load_keypair_by_pubkey(pubkey: str) -> Keypair:
    path = settings.wallets_dir / f"{pubkey}.json"
    if not path.exists():
        raise FileNotFoundError(f"Wallet {pubkey} not found")
    with open(path) as f:
        data = json.load(f)
    return Keypair.from_bytes(bytes(data["private_key"]))