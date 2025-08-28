from spl.token.instructions import burn, BurnParams
from spl.token.constants import TOKEN_PROGRAM_ID

from ..core.client import SolanaClient
from ..core.logger import logger
from ..services.liquidity_pool import load_from_json

async def burn_lp(solana_client: SolanaClient):
    tx_data = load_from_json()

    owner_lp_balance = await solana_client.get_token_account_balance(tx_data.creator_lp_token)

    if owner_lp_balance == 0:
        owner_lp_balance = tx_data.lp_amount
    burn_ix = burn(
        BurnParams(
            program_id=TOKEN_PROGRAM_ID,
            account=tx_data.creator_lp_token,
            mint=tx_data.lp_mint,
            owner=tx_data.creator_kp.pubkey(),
            amount=owner_lp_balance
        )
    )
    try:
        await solana_client.build_and_send_transaction(
            instructions=[burn_ix],
            msg_signer=tx_data.creator_kp,
            signers_keypairs=[tx_data.creator_kp],
            label="BURN"
        )
    except Exception as e:
        logger.exception(e)

    logger.info("LP successfully BURNED!")