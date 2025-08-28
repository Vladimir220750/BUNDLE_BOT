import typing
from solders.instruction import Instruction, AccountMeta

from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solana.rpc.types import MemcmpOpts
from spl.token.constants import TOKEN_2022_PROGRAM_ID
from construct import Struct, Int8ul, Int16ul, Int64ul
from spl.token.instructions import create_idempotent_associated_token_account, get_associated_token_address

from ..dto import BuildSwapInstructionRequest
from ..core.client import SolanaClient
from ..core.logger import logger
from ..core.wallet_manager import WalletManager, Wallet
from ..enums import Role
from .extensions import fetch_transfer_fee_config
from ..services.utils import get_external_ix

MAXIMUM_WITHDRAW_IX = 3
MAXIMUM_WITHDRAW_SOURCES = 10

def encode_optional_pubkey(pubkey: Pubkey | None) -> bytes:
    if pubkey is None:
        return bytes([0])
    return bytes([1]) + bytes(pubkey)

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
        program_id=TOKEN_2022_PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        ],
        data=data,
    )

def build_withdraw_fee_from_mint_ix(
    mint: Pubkey,
    fee_receiver: Pubkey,
    authority: Pubkey,
    program_id: Pubkey = TOKEN_2022_PROGRAM_ID
) -> Instruction:

    data = bytes([26, 2])

    accounts = [
        AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        AccountMeta(pubkey=fee_receiver, is_signer=False, is_writable=True),
        AccountMeta(pubkey=authority, is_signer=True, is_writable=False),
    ]

    return Instruction(
        accounts=accounts,
        program_id=program_id,
        data=data
    )

def build_withdraw_fee_from_accounts_ix(
    mint: Pubkey,
    fee_receiver: Pubkey,
    authority: Pubkey,
    sources: list[Pubkey],
    program_id: Pubkey = TOKEN_2022_PROGRAM_ID
) -> Instruction:

    if len(sources) > 20:
        raise ValueError("Can't place more then 20 source accounts.")

    data = bytes([26, 3, len(sources)])

    accounts = [
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=fee_receiver, is_signer=False, is_writable=True),
        AccountMeta(pubkey=authority, is_signer=True, is_writable=False),
    ]

    for acc in sources:
        accounts.append(AccountMeta(pubkey=acc, is_signer=False, is_writable=True))

    return Instruction(
        accounts=accounts,
        program_id=program_id,
        data=data
    )

async def withdraw_fee(
    mint: Pubkey,
    fee_receiver: typing.Optional[Keypair],
    authority: Keypair,
    solana_client: SolanaClient,
    wm: WalletManager,
):
    client = await solana_client.get_client()
    resp = await client.get_program_accounts_json_parsed(
        pubkey=TOKEN_2022_PROGRAM_ID,
        filters=[MemcmpOpts(offset=0, bytes=str(mint))],
    )

    if fee_receiver is None:
        fee_receiver_ATA = get_associated_token_address(
            mint=mint,
            owner=authority.pubkey(),
            token_program_id=TOKEN_2022_PROGRAM_ID
        )
        fee_receiver = authority
    else:
        fee_receiver_ATA = get_associated_token_address(
            mint=mint,
            owner=fee_receiver.pubkey(),
            token_program_id=TOKEN_2022_PROGRAM_ID
        )

    accounts = resp.value
    total_withheld = 0
    sources: list[Pubkey] = []

    for acc in accounts:
        pubkey = acc.pubkey
        parsed_info = acc.account.data.parsed["info"]
        extensions = parsed_info.get("extensions", [])
        withheld = 0

        for ext in extensions:
            if ext.get("extension") == "transferFeeAmount":
                withheld = ext.get("state", {}).get("withheldAmount", 0)
                break

        if withheld > 0:
            total_withheld += withheld
            sources.append(pubkey)

    if total_withheld <= 0:
        logger.error("TOTAL WITHHELD ZERO!")
        return

    try:
        swap_ixs: list[Instruction] = await get_external_ix(
            BuildSwapInstructionRequest(
                wallet=Wallet.from_keypair(fee_receiver).to_export(),
                amount=total_withheld,
                is_buy=False,
            )
        )
    except Exception as e:
        logger.error(f"Error while swaping, cancel: {e}")
        return

    instructions = [create_idempotent_associated_token_account(
        owner=fee_receiver.pubkey(),
        payer=authority.pubkey(),
        mint=mint,
        token_program_id=TOKEN_2022_PROGRAM_ID
    ), build_withdraw_fee_from_mint_ix(
        fee_receiver=fee_receiver_ATA,
        authority=authority.pubkey(),
        mint=mint,
    )]

    BATCH_SIZE = MAXIMUM_WITHDRAW_SOURCES
    for i in range(0, len(sources), BATCH_SIZE):
        chunk = sources[i:i + BATCH_SIZE]
        ix = build_withdraw_fee_from_accounts_ix(
            mint=mint,
            fee_receiver=fee_receiver_ATA,
            authority=authority.pubkey(),
            sources=chunk,
        )
        instructions.append(ix)

    logger.info(f"Prepared {len(instructions)} withdraw-from-accounts instructions ({MAXIMUM_WITHDRAW_SOURCES} per tx)")

    for batch_index, i in enumerate(range(0, len(instructions), MAXIMUM_WITHDRAW_IX)):
        batched_ixs = instructions[i:i + MAXIMUM_WITHDRAW_IX]
        label = f"WITHDRAW BATCH #{batch_index + 1}"
        try:
            '''logger.info(await solana_client.simulate_transaction(
                instructions=batched_ixs,
                msg_signer=dev.keypair,
                signers_keypairs=[dev.keypair],
            ))'''
            await solana_client.build_and_send_transaction(
                instructions=batched_ixs,
                msg_signer=authority,
                signers_keypairs=[authority],
                label=label,
                priority_fee=20000,
                max_retries=1,
                max_confirm_retries=5,
            )
            logger.info(f"Sent {label}")
        except Exception as e:
            logger.error(f"Failed to send {label}: {e}")

    logger.info("✅ All withdraw batches processed. SELLING NOW")
    label = f"SELL ALL FEES"
    try:
        '''logger.info(await solana_client.simulate_transaction(
            instructions=batched_ixs,
            msg_signer=dev.keypair,
            signers_keypairs=[dev.keypair],
        ))'''
        await solana_client.build_and_send_transaction(
            instructions=swap_ixs,
            msg_signer=fee_receiver,
            signers_keypairs=[fee_receiver],
            label=label,
            priority_fee=20000,
            max_retries=1,
            max_confirm_retries=5,
        )
        logger.info(f"Sent {label}")
    except Exception as e:
        logger.error(f"Failed to send {label}: {e}")

    logger.info("✅ SELL SUCCESS")