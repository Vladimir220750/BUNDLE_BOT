import json

from solders.pubkey import Pubkey
from .core.constants import (
    AMM_CONFIG_SEED,
    AUTH_SEED,
    POOL_SEED,
    POOL_VAULT_SEED,
    POOL_LP_MINT_SEED,
    OBSERVATION_SEED,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_PROGRAM_ID,
)
from .core.config import settings
from .core.dto import CONFIGDTO

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

def load_config() -> CONFIGDTO:
    tmp_dir = settings.tmp_dir
    config_name = "config.json"
    with open(tmp_dir / config_name, "r") as f:
        config = json.load(f)

    return CONFIGDTO(**config)

def save_config(data: CONFIGDTO) -> None:
    tmp_dir = settings.tmp_dir
    config_name = "config.json"
    with open(tmp_dir / config_name, "w") as f:
        json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)