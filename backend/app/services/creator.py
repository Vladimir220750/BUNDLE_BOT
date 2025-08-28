from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from .utils import (
    pack_create_data,
    get_mint_authority,
)
from ..core.wallet_manager import Wallet
from ..dto import TokenDTO
from ..core.constants import (
    PUMP_PROGRAM,
    PUMP_EVENT_AUTHORITY,
    PUMP_GLOBAL,
    SYSTEM_PROGRAM,
    SYSTEM_TOKEN_PROGRAM,
    MPL_TOKEN_METADATA_ID,
    SYSTEM_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM,
    RENT_SYSVAR_ID,
)

async def create_token_prepare_instruction(
    dev: Wallet,
    mint_info: TokenDTO,
) -> Instruction:

    #Types
    dev_pub: Pubkey
    bonding_curve: Pubkey
    associated_bonding_curve: Pubkey
    mint_authority: Pubkey
    metadata: Pubkey
    ######

    # Accounts Data
    # KeyPairs

    # PubKeys
    mint_pub: Pubkey = Pubkey.from_string(mint_info.mint_address)
    bonding_curve = Pubkey.from_string(mint_info.bonding_curve)
    associated_bonding_curve = Pubkey.from_string(mint_info.associated_bonding_curve)
    metadata = Pubkey.from_string(mint_info.metadata)
    dev_pub = dev.pubkey
    mint_authority, _ = await get_mint_authority()

    # Metadata of the Token
    name = mint_info.name
    symbol = mint_info.symbol
    uri = mint_info.uri
    creator = dev_pub
    # Get Packing Data
    data = pack_create_data(name, symbol, uri, creator)

    accounts = [
        AccountMeta(pubkey=mint_pub, is_signer=True, is_writable=True), # mint True, True
        AccountMeta(pubkey=mint_authority, is_signer=False, is_writable=False), # mint authority False, False
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True), # bonding curve False, True
        AccountMeta(pubkey=associated_bonding_curve, is_signer=False, is_writable=True), # ass_bonding_curve False, True
        AccountMeta(pubkey=PUMP_GLOBAL, is_signer=False, is_writable=False), # global False False
        AccountMeta(pubkey=MPL_TOKEN_METADATA_ID, is_signer=False, is_writable=False), # mpl_token_metadata False, False
        AccountMeta(pubkey=metadata, is_signer=False, is_writable=True), # metadata False, True
        AccountMeta(pubkey=dev_pub, is_signer=True, is_writable=True),  # user True, True
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False), # system_program False, False
        AccountMeta(pubkey=SYSTEM_TOKEN_PROGRAM, is_signer=False, is_writable=False), # token program False, False
        AccountMeta(pubkey=SYSTEM_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM, is_signer=False, is_writable=False), # ass token program False, False
        AccountMeta(pubkey=RENT_SYSVAR_ID, is_signer=False, is_writable=False), # rent False, False
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False), # event authority False, False
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False), # program False, False
    ]

    create_ix = Instruction(
        program_id=PUMP_PROGRAM,
        data=data,
        accounts=accounts
    )

    return create_ix