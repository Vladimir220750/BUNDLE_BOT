from fastapi import APIRouter, Depends
from solders.solders import Pubkey

from ..core.dc import DataCollector
from ..core.dto import InitializeRequest, Wallet, BuildSwapInstructionRequest, SerializedInstruction, LiquidityPoolData
from ..deps.dc import get_dc
from ..deps.solana_client import get_solana_client

from ..core.client import SolanaClient
from ..services.burn import burn_lp
from ..services.buyer import prepare_swap_base_in
from ..services.initialize_pool import initialize_pool
from ..services.liquidity_pool import load_from_json, save_to_json
from ..services.withdraw import withdraw

router = APIRouter()

@router.post("/initialize/")
async def initialize(
    data: InitializeRequest,
    client: SolanaClient = Depends(get_solana_client)
):
    sniper_wallets = []
    if data.sniper_wallets:
        sniper_wallets = [Wallet.from_dict(w) for w in data.sniper_wallets]

    await initialize_pool(
        solana_client=client,
        token_amount_ui=data.token_amount_ui,
        wsol_amount_ui=data.wsol_amount_ui,
        dev_wallet=Wallet.from_dict(data.dev_wallet),
        sniper_wallets=sniper_wallets,
        snipe_amount_ui=data.snipe_amount_ui,
        created_token_string=data.created_token_sting,
        transfer_fee=data.transfer_fee
    )

@router.post("/withdraw/")
async def withdraw_(
    client: SolanaClient = Depends(get_solana_client)
):
    await withdraw(
        solana_client=client,
    )

@router.get("/is-initialized/")
async def is_initialized():
    tx_data = load_from_json()
    return tx_data.initialized

@router.post("/toggle-initialized/")
async def toggle_initialized():
    tx_data = load_from_json()
    tx_data.initialized = not tx_data.initialized
    save_to_json(tx_data)
    return tx_data.initialized

@router.get("/dc-restart/")
async def dc_restart(dc: DataCollector = Depends(get_dc)):
    await dc.stop()
    await dc.start()

@router.get("/burn-lp/")
async def burn_lp_(solana_client: SolanaClient = Depends(get_solana_client)):
    await burn_lp(solana_client=solana_client)

@router.post("/instructions/swap_base_input/")
async def build_swap_base_input(
    data: BuildSwapInstructionRequest,
):
    instructions = await prepare_swap_base_in(
        wallet=Wallet.from_dict(data.wallet),
        amount=data.amount,
        is_buy=data.is_buy
    )
    return [SerializedInstruction.from_instruction(ix) for ix in instructions]

@router.get("/pool-data/")
async def get_liq_pool_data():
    return LiquidityPoolData.to_json_dict(load_from_json())