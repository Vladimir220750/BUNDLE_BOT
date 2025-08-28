from typing import Final, Optional

from solders.instruction import AccountMeta, Instruction
import struct

from solders.solders import Pubkey

from ..core.dto import LiquidityPoolData
from ..core.constants import (
    RAYDIUM_CP_PROGRAM_ID,
    CREATE_POOL_FEE_RECEIVER_ID,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_ACCOUNT_PROGRAM,
    SYS_VAR_RENT_ID,
    SYS_PROGRAM_ID, TOKEN_PROGRAM_2022_ID, MEMO_PROGRAM_ID, AMM_CONFIG_INDEX
)
from ..utils import (
    get_amm_config_address,
    get_authority_address,
)

WITHDRAW_DISCRIMINATOR: Final[bytes] = bytes([183, 18, 70, 156, 148, 109, 161, 34])
SWAP_BASE_INPUT_DISCRIMINATOR = bytes([143, 190, 90, 218, 196, 30, 51, 222])
INITIALIZE_DISCRIMINATOR: Final[bytes] = bytes([175, 175, 109, 31, 13, 152, 155, 237])

def build_initialize_pool_ix(
    tx_data: LiquidityPoolData,
    open_time_unix: int,
) -> Instruction:

    data = (
            INITIALIZE_DISCRIMINATOR +
            struct.pack("<Q", tx_data.token_mint0_amount) +
            struct.pack("<Q", tx_data.token_mint1_amount) +
            struct.pack("<Q", open_time_unix)
    )
    amm_config_pub = get_amm_config_address(index=AMM_CONFIG_INDEX, program_id=RAYDIUM_CP_PROGRAM_ID)
    authority = get_authority_address(program_id=RAYDIUM_CP_PROGRAM_ID)
    accounts = [
        AccountMeta(tx_data.creator_kp.pubkey(), is_signer=True, is_writable=True),   # creator
        AccountMeta(amm_config_pub, is_signer=False, is_writable=False), # amm_config
        AccountMeta(authority, is_signer=False, is_writable=False), # authority
        AccountMeta(tx_data.pool_state, is_signer=tx_data.random_pool_id is not None, is_writable=True),  # pool_state
        AccountMeta(tx_data.token_mint0, is_signer=False, is_writable=False), # token_0_mint
        AccountMeta(tx_data.token_mint1, is_signer=False, is_writable=False), # token_1_mint
        AccountMeta(tx_data.lp_mint, is_signer=False, is_writable=True),  # lp_mint
        AccountMeta(tx_data.creator_token0, is_signer=False, is_writable=True),  # creator_token_0
        AccountMeta(tx_data.creator_token1, is_signer=False, is_writable=True),  # creator_token_1
        AccountMeta(tx_data.creator_lp_token, is_signer=False, is_writable=True),  # creator_lp_token
        AccountMeta(tx_data.token0_vault, is_signer=False, is_writable=True),  # token_0_vault
        AccountMeta(tx_data.token1_vault, is_signer=False, is_writable=True),  # token_1_vault
        AccountMeta(CREATE_POOL_FEE_RECEIVER_ID, is_signer=False, is_writable=True),  # create_pool_fee
        AccountMeta(tx_data.observation, is_signer=False, is_writable=True),  # observation_state
        AccountMeta(TOKEN_PROGRAM_ID, is_signer=False, is_writable=False), # token_program
        AccountMeta(tx_data.token_0_program, is_signer=False, is_writable=False), # token_0_program
        AccountMeta(tx_data.token_1_program, is_signer=False, is_writable=False), # token_1_program
        AccountMeta(ASSOCIATED_TOKEN_ACCOUNT_PROGRAM, is_signer=False, is_writable=False), # associated_token_program
        AccountMeta(SYS_PROGRAM_ID, is_signer=False, is_writable=False),  # system_program
        AccountMeta(SYS_VAR_RENT_ID, is_signer=False, is_writable=False), # rent
    ]
    return Instruction(
        program_id=RAYDIUM_CP_PROGRAM_ID,
        data=data,
        accounts=accounts,
    )

def build_withdraw_ix(
    *,
    tx_data: LiquidityPoolData,
    lp_token_amount: int,
    min_token_0: int = 0,
    min_token_1: int = 0,
) -> Instruction:

    data = (
        WITHDRAW_DISCRIMINATOR +
        struct.pack("<Q", lp_token_amount) +
        struct.pack("<Q", min_token_0) +
        struct.pack("<Q", min_token_1)
    )
    accounts = [
        AccountMeta(pubkey=tx_data.creator_kp.pubkey(), is_signer=True, is_writable=True),
        AccountMeta(pubkey=tx_data.authority, is_signer=False, is_writable=False),
        AccountMeta(pubkey=tx_data.pool_state, is_signer=False, is_writable=True),
        AccountMeta(pubkey=tx_data.creator_lp_token, is_signer=False, is_writable=True),
        AccountMeta(pubkey=tx_data.token_0_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=tx_data.token_1_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=tx_data.token0_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=tx_data.token1_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM_2022_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=tx_data.token_mint0, is_signer=False, is_writable=False),
        AccountMeta(pubkey=tx_data.token_mint1, is_signer=False, is_writable=False),
        AccountMeta(pubkey=tx_data.lp_mint, is_signer=False, is_writable=True),
        AccountMeta(pubkey=MEMO_PROGRAM_ID, is_signer=False, is_writable=False),
    ]
    return Instruction(
        program_id=RAYDIUM_CP_PROGRAM_ID,
        data=data,
        accounts=accounts,
    )

def build_swap_ix(
    *,
    tx_data: LiquidityPoolData,
    payer: Pubkey,
    input_token_account: Pubkey,
    output_token_account: Pubkey,
    input_mint: Pubkey,
    output_mint: Pubkey,
    input_vault: Pubkey,
    output_vault: Pubkey,
    input_program: Pubkey,
    output_program: Pubkey,
    amount_in: int,
    minimum_amount_out: int = 0,
) -> Instruction:

    data = (
        SWAP_BASE_INPUT_DISCRIMINATOR +
        struct.pack("<Q", amount_in) +
        struct.pack("<Q", minimum_amount_out)
    )

    amm_config = get_amm_config_address(index=AMM_CONFIG_INDEX, program_id=RAYDIUM_CP_PROGRAM_ID)
    accounts = [
        AccountMeta(payer, is_signer=True, is_writable=True),
        AccountMeta(tx_data.authority, is_signer=False, is_writable=False),
        AccountMeta(amm_config, is_signer=False, is_writable=False),
        AccountMeta(tx_data.pool_state, is_signer=False, is_writable=True),
        AccountMeta(input_token_account, is_signer=False, is_writable=True),
        AccountMeta(output_token_account, is_signer=False, is_writable=True),
        AccountMeta(input_vault, is_signer=False, is_writable=True),
        AccountMeta(output_vault, is_signer=False, is_writable=True),
        AccountMeta(input_program, is_signer=False, is_writable=False),
        AccountMeta(output_program, is_signer=False, is_writable=False),
        AccountMeta(input_mint, is_signer=False, is_writable=False),
        AccountMeta(output_mint, is_signer=False, is_writable=False),
        AccountMeta(tx_data.observation, is_signer=False, is_writable=True),
    ]

    return Instruction(
        program_id=RAYDIUM_CP_PROGRAM_ID,
        data=data,
        accounts=accounts,
    )
