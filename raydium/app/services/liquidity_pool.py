import math
from typing import Optional
import json
from pathlib import Path
from solders.solders import Pubkey, Keypair
from spl.token.instructions import get_associated_token_address

from ..core.dto import LiquidityPoolData
from ..core.constants import (
    RAYDIUM_CP_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    SOL_WRAPPED_MINT,
    TOKEN_PROGRAM_2022_ID,
    AMM_CONFIG_INDEX
)
from ..utils import (
    get_amm_config_address,
    get_authority_address,
    get_pool_address,
    get_pool_lp_mint_address,
    get_pool_vault_address,
    get_oracle_account_address
)

DEFAULT_LIQ_POOL_PATH = Path(__file__).parent.parent / "liq_pool" / "latest_pool.json"

def get_token_amount_after_fee(amount: int, fee_percent: int) -> int:
    """
    Returns the amount after subtracting a percentage-based fee.
    """
    return int(amount * (100 - fee_percent) / 100)

def calculate_lp_tokens(vault_0: int, vault_1: int, lock_lp: int = 100) -> int:
    raw = math.isqrt(vault_0 * vault_1)
    return raw - lock_lp

def save_to_json(data: LiquidityPoolData, path: Path = DEFAULT_LIQ_POOL_PATH):
    DEFAULT_LIQ_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data.to_json_dict(), f, indent=2)

def load_from_json(path: Path = DEFAULT_LIQ_POOL_PATH) -> LiquidityPoolData:
    with open(path, "r") as f:
        raw = json.load(f)
    return LiquidityPoolData.from_json_dict(raw)

def prepare_liquidity_pool_data(
    *,
    creator: Keypair,
    created_token_mint: Pubkey,
    created_token_ata: Pubkey,
    sol_ata: Pubkey,
    token_amount: int,
    wsol_amount: int,
    random_pool_id: Optional[Pubkey] = None,
    transfer_fee: int = 0, # percent: 8 = 8%, 10 = 10%
) -> LiquidityPoolData:
    """
    Подготовка и сохранение всех параметров пула для дальнейшего использования.
    """

    is_token_first = bytes(created_token_mint) < bytes(SOL_WRAPPED_MINT)

    token_mint0 = created_token_mint if is_token_first else SOL_WRAPPED_MINT
    token_mint1 = SOL_WRAPPED_MINT if is_token_first else created_token_mint

    creator_token0 = created_token_ata if is_token_first else sol_ata
    creator_token1 = sol_ata if is_token_first else created_token_ata

    token_0_program = TOKEN_PROGRAM_2022_ID if is_token_first else TOKEN_PROGRAM_ID
    token_1_program = TOKEN_PROGRAM_ID if is_token_first else TOKEN_PROGRAM_2022_ID

    token_mint0_amount = token_amount if is_token_first else wsol_amount
    token_mint1_amount = wsol_amount if is_token_first else token_amount

    token_0_ata = created_token_ata if is_token_first else sol_ata
    token_1_ata = sol_ata if is_token_first else created_token_ata

    amm_config_pub = get_amm_config_address(index=AMM_CONFIG_INDEX, program_id=RAYDIUM_CP_PROGRAM_ID)
    authority = get_authority_address(program_id=RAYDIUM_CP_PROGRAM_ID)
    pool_state = random_pool_id or get_pool_address(
        amm_config=amm_config_pub,
        token_mint0=token_mint0,
        token_mint1=token_mint1,
        program_id=RAYDIUM_CP_PROGRAM_ID
    )
    lp_mint = get_pool_lp_mint_address(pool_state, RAYDIUM_CP_PROGRAM_ID)
    creator_lp_token = get_associated_token_address(owner=creator.pubkey(), mint=lp_mint)
    token0_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=token_mint0, program_id=RAYDIUM_CP_PROGRAM_ID)
    token1_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=token_mint1, program_id=RAYDIUM_CP_PROGRAM_ID)
    observation = get_oracle_account_address(pool=pool_state, program_id=RAYDIUM_CP_PROGRAM_ID)

    liq_vault = token1_vault if is_token_first else token0_vault

    data = LiquidityPoolData(
        creator_kp=creator,
        token_mint0=token_mint0,
        token_mint1=token_mint1,
        token_0_program=token_0_program,
        token_1_program=token_1_program,
        token_mint0_amount=token_mint0_amount,
        token_mint1_amount=token_mint1_amount,
        pool_state=pool_state,
        authority=authority,
        lp_mint=lp_mint,
        creator_lp_token=creator_lp_token,
        token0_vault=token0_vault,
        token1_vault=token1_vault,
        observation=observation,
        creator_token0=creator_token0,
        creator_token1=creator_token1,
        random_pool_id=random_pool_id,
        token_0_ata=token_0_ata,
        token_1_ata=token_1_ata,
        initialized=True,
        liq_vault=liq_vault,
        lp_amount=calculate_lp_tokens(get_token_amount_after_fee(token_amount, transfer_fee), wsol_amount),
    )
    save_to_json(data)
    return data
