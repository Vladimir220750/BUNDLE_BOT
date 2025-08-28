import asyncio

from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from spl.token.async_client import AsyncToken
from spl.token.constants import TOKEN_2022_PROGRAM_ID

RPC_URL = "https://lb.drpc.org/ogrpc?network=solana&dkey=Anel9UV-y0b6gj9ghgRejMrjRyztV4IR8JXsrqRhf0fE"
MINT_ADDRESS = Pubkey.from_string("G2jSA9WbGF9E3nAQBTnvsGjpYXTBKvmX1LEvzpccD9uh")
DESTINATION_ATA = Pubkey.from_string("9YgBccx26E8qdVA13Q4ore2JVauchR7vcwMNiKdxN4DJ")
AMOUNT = 5

payer = Keypair.from_base58_string("3sg2UqgKvbL9EeAZJrmwV9dvNAG9UAbvoF7k5qhjgijrkLGmrwd4nSwE6qjZmhxyrwVr2vWxaH3i7duEpxPu29vn")

async def mint_existing_token():
    client = AsyncClient(RPC_URL)
    token = AsyncToken(client, MINT_ADDRESS, TOKEN_2022_PROGRAM_ID, payer)

    tx_sig = await token.mint_to(
        dest=DESTINATION_ATA,
        mint_authority=payer,
        amount=AMOUNT,
        opts=TxOpts(
            skip_preflight=True
        )
    )

    print(f"Minted {AMOUNT} tokens, tx: {tx_sig}")
    await client.close()

asyncio.run(mint_existing_token())
