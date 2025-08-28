import asyncio
from spl.token.constants import WRAPPED_SOL_MINT
from spl.token.instructions import create_idempotent_associated_token_account

from ..core.client import SolanaClient
from ..instructions.amm_pool import build_withdraw_ix
from ..services.liquidity_pool import load_from_json
from ..core.logger import logger

async def withdraw(
    solana_client: SolanaClient,
):
    tx_data = load_from_json()
    owner_lp_balance = await solana_client.get_token_account_balance(tx_data.creator_lp_token)

    if owner_lp_balance == 0:
        owner_lp_balance = tx_data.lp_amount

    withdraw_ix = build_withdraw_ix(
        tx_data=tx_data,
        lp_token_amount=owner_lp_balance,
    )
    create_wsol_ata_ix = create_idempotent_associated_token_account(
        payer=tx_data.creator_kp.pubkey(),
        owner=tx_data.creator_kp.pubkey(),
        mint=WRAPPED_SOL_MINT,

    )
    try:
        await solana_client.build_and_send_transaction(
            instructions=[create_wsol_ata_ix, withdraw_ix],
            msg_signer=tx_data.creator_kp,
            signers_keypairs=[tx_data.creator_kp],
            priority_fee=50000,
            max_retries=1,
            label="WITHDRAW",
            jito_tip=500_000, # 0.0005 SOL
        )
        await solana_client.build_and_send_transaction(
            instructions=[create_wsol_ata_ix, withdraw_ix],
            msg_signer=tx_data.creator_kp,
            signers_keypairs=[tx_data.creator_kp],
            priority_fee=50000,
            max_retries=1,
            label="WITHDRAW",
        )
    except Exception as e:
        logger.error("ALARM! WITHDRAW NOT SUCCESS. TRY AGAIN NOW!")
        logger.exception(e)
        raise
