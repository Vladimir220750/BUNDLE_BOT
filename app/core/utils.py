import math
from solders.pubkey import Pubkey
from .constants import (
    AMM_CONFIG_SEED,
    AUTH_SEED,
    POOL_SEED,
    POOL_VAULT_SEED,
    POOL_LP_MINT_SEED,
    OBSERVATION_SEED,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    LAMPORTS_PER_SOL,
    MILLION
)

def u16_to_bytes(value: int) -> bytes:
    return value.to_bytes(2, "big")

def get_amm_config_address(index: int, program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address([AMM_CONFIG_SEED, u16_to_bytes(index)], program_id)
    return result

def get_authority_address(program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address([AUTH_SEED], program_id)
    return result

def get_pool_address(amm_config: Pubkey, token_mint0: Pubkey, token_mint1: Pubkey, program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address(
        [POOL_SEED, bytes(amm_config), bytes(token_mint0), bytes(token_mint1)], program_id
    )
    return result

def get_pool_vault_address(pool: Pubkey, vault_token_mint: Pubkey, program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address(
        [POOL_VAULT_SEED, bytes(pool), bytes(vault_token_mint)], program_id
    )
    return result

def get_pool_lp_mint_address(pool: Pubkey, program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address([POOL_LP_MINT_SEED, bytes(pool)], program_id)
    return result

def get_creator_lp_mint(creator: Pubkey, lp_mint: Pubkey):
    result, _ = Pubkey.find_program_address(
        [bytes(creator), bytes(TOKEN_PROGRAM_ID), bytes(lp_mint)], ASSOCIATED_TOKEN_PROGRAM_ID
    )
    return result

def get_oracle_account_address(pool: Pubkey, program_id: Pubkey) -> (Pubkey, int):
    result, _ = Pubkey.find_program_address([OBSERVATION_SEED, bytes(pool)], program_id)
    return result

def sol_to_lamports(amount_sol: float) -> int:
    return int(amount_sol * LAMPORTS_PER_SOL)

def lamports_to_sol(amount_lamports: int) -> float:
    return float(amount_lamports) / LAMPORTS_PER_SOL

def tokens_ui_to_base_units(amount_tokens_ui: float, decimals: int) -> int:
    """Convert tokens ui (10 Millions tokens) to base_units (10_000_000_000_000_000)"""
    return int(amount_tokens_ui * MILLION * 10 ** decimals)

def tokens_base_units_to_ui(amount_base_units: float, decimals: int) -> float:
    """Convert tokens base_units (10_000_000_000_000_000) to UI (10 Millions tokens)"""
    return float(amount_base_units / MILLION / 10 ** decimals)

def get_token_amount_after_fee(amount: int, fee_percent: int) -> int:
    """
    Returns the amount after subtracting a percentage-based fee.
    """
    return int(amount * (100 - fee_percent) / 100)

def calculate_lp_tokens(vault_0: int, vault_1: int, lock_lp: int = 100) -> int:
    raw = math.isqrt(vault_0 * vault_1)
    return raw - lock_lp