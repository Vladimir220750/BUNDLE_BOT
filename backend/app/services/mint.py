from spl.token.constants import TOKEN_2022_PROGRAM_ID
from spl.token.instructions import mint_to_checked, MintToCheckedParams, create_idempotent_associated_token_account, AccountMeta

from solders.system_program import create_account, CreateAccountParams
from construct import Struct, Int8ul, Bytes, Flag

from ..core.constants import SYS_VAR_RENT_ID
from ..core.client import SolanaClient
from ..core.wallet_manager import Wallet
from ..dto import BuildSwapInstructionRequest
from ..services.utils import get_external_ix
from typing import Optional
from ..core.constants import TOKEN_WITH_DECIMALS, DECIMALS, TOKEN_DECIMALS
from ..core.logger import logger

from solders.solders import Pubkey, Instruction

MINT_ACCOUNT_SPACE =  346 # with transfer fee config
SPACE_FOR_RENT = 600

def encode_optional_pubkey(pubkey: Optional[Pubkey]) -> bytes:
    if pubkey is None:
        return bytes([0])
    return bytes([1]) + bytes(pubkey)


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
        program_id=TOKEN_2022_PROGRAM_ID,
        accounts=[
            AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
            AccountMeta(pubkey=SYS_VAR_RENT_ID, is_signer=False, is_writable=False),
        ],
        data=data,
    )

async def build_create_mint_account_ix(
    payer: Pubkey,
    mint: Pubkey,
    solana_client: SolanaClient
) -> Instruction:

    lamports = await solana_client.get_minimum_balance_for_rent_exemption(SPACE_FOR_RENT)
    return create_account(
        CreateAccountParams(
            from_pubkey=payer,
            to_pubkey=mint,
            lamports=lamports,
            space=MINT_ACCOUNT_SPACE,
            owner=TOKEN_2022_PROGRAM_ID,
        )
    )

async def mint_to_and_sell(
    mint_address: Pubkey,
    solana_client: SolanaClient,
    dev_wallet: Wallet,
    amount: int,
    dest_wallet: Optional[Wallet] = None,
):
    try:
        ixs = []
        signers = [dev_wallet.keypair]
        dest = dev_wallet.get_ata(mint_address, token_program=TOKEN_2022_PROGRAM_ID)
        if dest_wallet:
            dest = dest_wallet.get_ata(mint_address, token_program=TOKEN_2022_PROGRAM_ID)
            create_ata_ix = create_idempotent_associated_token_account(
                payer=dest_wallet.pubkey,
                owner=dest_wallet.pubkey,
                mint=mint_address,
                token_program_id=TOKEN_2022_PROGRAM_ID
            )
            ixs.append(create_ata_ix)
            signers.append(dest_wallet.keypair)

        amount = amount * 1_000_000
        decimal_amount = amount * TOKEN_WITH_DECIMALS

        ixs.append(mint_to_checked(
            MintToCheckedParams(
                program_id=TOKEN_2022_PROGRAM_ID,
                mint=mint_address,
                dest=dest,
                mint_authority=dev_wallet.pubkey,
                amount=decimal_amount,
                decimals=TOKEN_DECIMALS,
                signers=[dev_wallet.pubkey],
            )
        ))

        swap_ixs: list[Instruction] = await get_external_ix(
            BuildSwapInstructionRequest(
                wallet=dest_wallet.to_export() if dest_wallet else dev_wallet.to_export(),
                amount=decimal_amount,
                is_buy=False,
            )
        )

        ixs.extend(swap_ixs)
        tx_sig = await solana_client.build_and_send_transaction(
            instructions=ixs,
            msg_signer=dev_wallet.keypair,
            signers_keypairs=signers,
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=30_000,
            label="Mint and Sell"
        )

        logger.info(f"Minted {amount} tokens, tx: {tx_sig}")
    except Exception as e:
        logger.debug(e)
