from typing import Final, Optional

from solders.instruction import AccountMeta, Instruction
import struct

from solders.solders import Pubkey

from .dto import LiquidityPoolData
from .constants import (
    RAYDIUM_CP_PROGRAM_ID,
    CREATE_POOL_FEE_RECEIVER_ID,
    TOKEN_PROGRAM_ID,
    ASSOCIATED_TOKEN_ACCOUNT_PROGRAM,
    SYS_VAR_RENT_ID,
    SYS_PROGRAM_ID,
    TOKEN_PROGRAM_2022_ID,
    MEMO_PROGRAM_ID,
    AMM_CONFIG_INDEX,
)

from .utils import (
    get_amm_config_address,
    get_authority_address,
)

from construct import Struct, Bytes, Int32ul, Int16ul, Int64ul, Int8ul

WITHDRAW_DISCRIMINATOR: Final[bytes] = bytes([183, 18, 70, 156, 148, 109, 161, 34])
SWAP_BASE_INPUT_DISCRIMINATOR = bytes([143, 190, 90, 218, 196, 30, 51, 222])
INITIALIZE_DISCRIMINATOR: Final[bytes] = bytes([175, 175, 109, 31, 13, 152, 155, 237])

METADATA_DISCRIMINATOR = bytes.fromhex("d2e11ea258b84d8d")

MetadataStruct = Struct(
    "discriminator" / Bytes(8),
    "name" / Int32ul >> Bytes(lambda ctx: len(ctx._.name.encode("utf-8"))),
    "symbol" / Int32ul >> Bytes(lambda ctx: len(ctx._.symbol.encode("utf-8"))),
    "uri" / Int32ul >> Bytes(lambda ctx: len(ctx._.uri.encode("utf-8"))),
)

METADATA_POINTER_DISCRIMINATOR = 39
METADATA_POINTER_SUB_DISCRIMINATOR = 0

def encode_zeroable_option(pubkey: Pubkey | None) -> bytes:
    if pubkey is None:
        return b'\x00' * 32
    return bytes(pubkey)

def encode_string(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return Int32ul.build(len(encoded)) + encoded

def encode_optional_pubkey(pubkey: Pubkey | None) -> bytes:
    if pubkey is None:
        return bytes([0])
    return bytes([1]) + bytes(pubkey)

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

def build_initialize_metadata_pointer_ix(
    mint: Pubkey,
    authority: Pubkey | None,
    metadata_address: Pubkey | None,
) -> Instruction:
    data = bytes([
        METADATA_POINTER_DISCRIMINATOR,
        METADATA_POINTER_SUB_DISCRIMINATOR
    ]) + encode_zeroable_option(authority) + encode_zeroable_option(metadata_address)

    return Instruction(
        program_id=TOKEN_PROGRAM_2022_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        ],
        data=data
    )

def build_initialize_token_metadata_ix(
    metadata: Pubkey,
    update_authority: Pubkey,
    mint: Pubkey,
    mint_authority: Pubkey,
    name: str,
    symbol: str,
    uri: str
) -> Instruction:
    data = (
        METADATA_DISCRIMINATOR +
        encode_string(name) +
        encode_string(symbol) +
        encode_string(uri)
    )

    return Instruction(
        program_id=TOKEN_PROGRAM_2022_ID,
        accounts=[
            AccountMeta(pubkey=metadata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=update_authority, is_signer=False, is_writable=False),
            AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=mint_authority, is_signer=True, is_writable=False),
        ],
        data=data
    )

def build_initialize_transfer_fee_config_ix(
    mint: Pubkey,
    authority: Pubkey,
    basis_points: int,
    max_fee: int
) -> Instruction:

    discriminator = 26
    transfer_fee_discriminator = 0

    data = bytes([
        discriminator,
        transfer_fee_discriminator,
    ]) \
    + encode_optional_pubkey(authority) \
    + encode_optional_pubkey(authority) \
    + Int16ul.build(basis_points) \
    + Int64ul.build(max_fee)

    return Instruction(
        program_id=TOKEN_PROGRAM_2022_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        ],
        data=data,
    )

def build_initialize_mint_ix(
    mint: Pubkey,
    mint_authority: Pubkey,
    freeze_authority: Optional[Pubkey],
    decimals: int,
) -> Instruction:

    discriminator = Int8ul.build(0)
    decimals_bytes = Int8ul.build(decimals)
    mint_authority_bytes = bytes(mint_authority)
    freeze_authority_bytes = encode_optional_pubkey(freeze_authority)

    data = (
        discriminator
        + decimals_bytes
        + mint_authority_bytes
        + freeze_authority_bytes
    )

    return Instruction(
        program_id=TOKEN_PROGRAM_2022_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_VAR_RENT_ID, is_signer=False, is_writable=False),
        ],
        data=data,
    )