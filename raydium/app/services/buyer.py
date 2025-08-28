from solders.solders import Instruction

from solders.system_program import transfer, TransferParams
from ..instructions.amm_pool import build_swap_ix
from ..core.dto import Wallet
from ..services.liquidity_pool import load_from_json
from ..utils import get_pool_vault_address

from spl.token.instructions import (
    get_associated_token_address,
    create_idempotent_associated_token_account,
    sync_native,
    SyncNativeParams

)
from ..core.constants import SOL_WRAPPED_MINT, TOKEN_PROGRAM_2022_ID, LAMPORTS_PER_SOL, TOKEN_PROGRAM_ID, RAYDIUM_CP_PROGRAM_ID

async def prepare_swap_base_in(
    wallet: Wallet,
    amount: int,
    is_buy: bool = True,
) -> list[Instruction]:

    if amount <= 0:
        raise RuntimeError("Buy amount zero or less.")

    tx_data = load_from_json()

    pool_state = tx_data.pool_state

    if is_buy:
        input_mint = SOL_WRAPPED_MINT
        input_program = TOKEN_PROGRAM_ID
        output_mint = tx_data.token_mint0 if tx_data.token_mint0 != SOL_WRAPPED_MINT else tx_data.token_mint1
        output_program = TOKEN_PROGRAM_2022_ID
    else:
        input_mint = tx_data.token_mint0 if tx_data.token_mint0 != SOL_WRAPPED_MINT else tx_data.token_mint1
        input_program = TOKEN_PROGRAM_2022_ID
        output_mint = SOL_WRAPPED_MINT
        output_program = TOKEN_PROGRAM_ID

    input_ata = get_associated_token_address(
        owner=wallet.pubkey,
        mint=input_mint,
        token_program_id=TOKEN_PROGRAM_2022_ID if input_mint != SOL_WRAPPED_MINT else TOKEN_PROGRAM_ID,
    )
    output_ata = get_associated_token_address(
        owner=wallet.pubkey,
        mint=output_mint,
        token_program_id=TOKEN_PROGRAM_2022_ID if output_mint != SOL_WRAPPED_MINT else TOKEN_PROGRAM_ID,
    )

    create_input_ata_ix = create_idempotent_associated_token_account(
        payer=wallet.pubkey,
        owner=wallet.pubkey,
        mint=input_mint,
        token_program_id=TOKEN_PROGRAM_2022_ID if input_mint != SOL_WRAPPED_MINT else TOKEN_PROGRAM_ID,
    )
    create_output_ata_ix = create_idempotent_associated_token_account(
        payer=wallet.pubkey,
        owner=wallet.pubkey,
        mint=output_mint,
        token_program_id=TOKEN_PROGRAM_2022_ID if output_mint != SOL_WRAPPED_MINT else TOKEN_PROGRAM_ID,
    )

    instructions = [create_input_ata_ix, create_output_ata_ix]

    if is_buy:
        transfer_sol_ix = transfer(
            TransferParams(
                from_pubkey=wallet.pubkey,
                to_pubkey=input_ata,
                lamports=amount,
            )
        )
        sync_native_ix = sync_native(
            SyncNativeParams(
                account=input_ata,
                program_id=TOKEN_PROGRAM_ID,
            )
        )
        instructions.extend([transfer_sol_ix, sync_native_ix])

    input_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=input_mint,
                                          program_id=RAYDIUM_CP_PROGRAM_ID)
    output_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=output_mint,
                                          program_id=RAYDIUM_CP_PROGRAM_ID)

    swap_ix = build_swap_ix(
        tx_data=tx_data,
        payer=wallet.pubkey,
        input_token_account=input_ata,
        output_token_account=output_ata,
        input_mint=input_mint,
        output_mint=output_mint,
        input_vault=input_vault,
        output_vault=output_vault,
        input_program=input_program,
        output_program=output_program,
        amount_in=amount,
        minimum_amount_out=0,
    )
    instructions.append(swap_ix)

    return instructions
