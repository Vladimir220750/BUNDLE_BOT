from pathlib import Path
import asyncio
import sys
import json
import websockets
from spl.token.instructions import freeze_account, thaw_account, FreezeAccountParams, ThawAccountParams
from spl.token.constants import TOKEN_2022_PROGRAM_ID
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction

DEFAULT_LIQ_POOL_PATH = "./raydium/app/liq_pool/latest_pool.json"

FREEZE_AUTHORITY_SECRET_KEY = "4Xana3xvs7gihm7WnyaX1yFUU7eHnNmb9RfVMXzk7CybYzcfM8KFExPHxgjGAhLC6qiUCT6gQ75yoB8prgQoJxoJ"
freeze_authority = Keypair.from_base58_string(FREEZE_AUTHORITY_SECRET_KEY)

RPC_URL = "https://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2"
WS_URL = "wss://mainnet.helius-rpc.com/?api-key=0d620e29-1564-4720-8d27-8b9a3dff5ba2"

frozen_accounts = set()

ignore_list = [

]

def load_from_json(path: Path = DEFAULT_LIQ_POOL_PATH) -> dict:
    with open(path, "r") as f:
        return json.load(f)

async def send_freeze_instruction(token_account: Pubkey, mint: Pubkey):
    async with AsyncClient(RPC_URL) as client:
        ix = freeze_account(
            FreezeAccountParams(
                program_id=TOKEN_2022_PROGRAM_ID,
                account=token_account,
                mint=mint,
                authority=freeze_authority.pubkey()
            )
        )
        recent_blockhash = await client.get_latest_blockhash()
        message = Message([ix], freeze_authority.pubkey())
        tx_opts = TxOpts(
            skip_preflight=True, preflight_commitment=Processed
        )
        tx = Transaction([freeze_authority], message, recent_blockhash.value.blockhash)
        print(f"[→] Freezing {token_account}")
        resp = await client.send_transaction(tx, tx_opts)
        print(f"[✓] Sent freeze: {resp}")

async def send_thaw_instruction(token_account: Pubkey, mint: Pubkey):
    async with AsyncClient(RPC_URL) as client:
        ix = thaw_account(
            ThawAccountParams(
                program_id=TOKEN_2022_PROGRAM_ID,
                account=token_account,
                mint=mint,
                authority=freeze_authority.pubkey()
            )
        )
        recent_blockhash = await client.get_latest_blockhash()
        message = Message([ix], freeze_authority.pubkey())
        tx_opts = TxOpts(skip_preflight=True, preflight_commitment=Processed)
        tx = Transaction([freeze_authority], message, recent_blockhash.value.blockhash)
        print(f"[→] Thawing {token_account}")
        resp = await client.send_transaction(tx, tx_opts)
        print(f"[✓] Sent thaw: {resp}")

async def run_freeze_monitor(mint: Pubkey):
    print(f"[+] Subscribing to Token2022 activity for mint: {mint}")
    async with websockets.connect(WS_URL) as ws:
        sub_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "programSubscribe",
            "params": [
                str(TOKEN_2022_PROGRAM_ID),
                {
                    "encoding": "jsonParsed",
                    "filters": [
                        {"memcmp": {"offset": 0, "bytes": str(mint)}},
                    ]
                }
            ]
        }
        await ws.send(json.dumps(sub_request))
        await ws.recv()

        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            try:
                token_account_pubkey = Pubkey.from_string(data['params']['result']['value']['pubkey'])
                onwer_pub = Pubkey.from_string(data['params']['result']['value']['account']['data']['owner'])
                if token_account_pubkey in frozen_accounts or onwer_pub in ignore_list:
                    continue
                await send_freeze_instruction(token_account_pubkey, mint)
                frozen_accounts.add(token_account_pubkey)
            except Exception as e:
                print(f"[!] Error: {e}")

async def main():
    pool_data = load_from_json()
    mint = Pubkey.from_string(pool_data.get("token_mint1"))
    if len(sys.argv) >= 3 and sys.argv[1] == "unfreeze":
        token_account = Pubkey.from_string(sys.argv[2])
        await send_thaw_instruction(token_account, mint)
    else:
        ignore_pubs = [
            freeze_authority.pubkey(),
            Pubkey.from_string(pool_data.get("token0_vault")),
            Pubkey.from_string(pool_data.get("token1_vault")),
            Pubkey.from_string(pool_data.get("creator_lp_token")),
            Pubkey.from_string(pool_data.get("creator_token0")),
            Pubkey.from_string(pool_data.get("creator_token1")),
        ]
        for p in ignore_pubs:
            frozen_accounts.add(p)
        print(f"[+] Ignoring accounts:\n  " + "\n  ".join(str(p) for p in frozen_accounts))
        await run_freeze_monitor(mint)

if __name__ == "__main__":
    asyncio.run(main())
