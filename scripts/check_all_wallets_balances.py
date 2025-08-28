import json
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.async_api import AsyncClient

RPC_HTTP_URL = "https://lb.drpc.org/ogrpc?network=solana&dkey=Anel9UV-y0b6gj9ghgRejMrjRyztV4IR8JXsrqRhf0fE"

class Role(str, Enum):
    dev = "dev"
    fund = "fund"
    group1 = "group1"
    group2 = "group2"
    archive = "archive"

@dataclass
class Wallet:
    """
    Represents a single wallet used in the system.
    """
    name: str
    group: Role
    pubkey: Pubkey
    keypair: Keypair
    path: Optional[Path] = None

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            group=Role(data["group"]),
            name=data["name"],
            pubkey=Pubkey.from_string(data["pubkey"]),
            keypair=Keypair.from_bytes(bytes(data["private_key"])),
        )

def load_wallets(path: Path) -> list[Wallet]:
    """
    Load all wallets from filesystem and initialize Wallet objects.
    """
    wallets = []
    for file in path.glob("*.json"):
        with open(file) as f:
            data = json.load(f)
            wallet = Wallet.from_dict(data)
            wallet.path = path
            wallets.append(wallet)
    return wallets


async def check_balances(wallet_dirs: list[str]):
    client = AsyncClient(RPC_HTTP_URL)
    wallets: list[Wallet] = []

    for dir_name in wallet_dirs:
        folder_path = Path(dir_name)
        if not folder_path.exists() or not folder_path.is_dir():
            print(f"[!] Skipping non-existent folder: {folder_path}")
            continue
        try:
            wallets.extend(load_wallets(folder_path))
        except Exception as e:
            print(f"[!] Error loading wallets from {str(folder_path)}: {e}")

    pubkeys = [w.pubkey for w in wallets]
    resp = await client.get_multiple_accounts(pubkeys)

    print("\n=== BALANCE REPORT ===")
    for wallet, account_opt in zip(wallets, resp.value):
        if account_opt is None:
            print(f"[?] Unknown balance — {wallet.pubkey} (from {wallet.path.parent.name})")
            continue

        lamports = account_opt.lamports
        sol = lamports / 1_000_000_000
        if lamports > 0:
            print(f"[+] {sol:.9f} SOL — {wallet.pubkey} (from {wallet.path.parent.name})")
        else:
            print(f"[ ] 0 SOL — {wallet.pubkey} (from {wallet.path.parent.name})")

    await client.close()


if __name__ == "__main__":
    wallet_folders = ["wallets", "temp_wallets", "archive_wallets"]
    asyncio.run(check_balances(wallet_folders))