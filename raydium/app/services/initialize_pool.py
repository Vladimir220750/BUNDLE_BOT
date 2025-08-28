import random

import time
from typing import Optional

from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from spl.token.instructions import (
    get_associated_token_address,
    create_idempotent_associated_token_account,
    sync_native,
    SyncNativeParams
)

from .liquidity_pool import prepare_liquidity_pool_data
from .buyer import prepare_swap_base_in
from ..core.client import SolanaClient
from ..core.dto import Wallet
from ..instructions.amm_pool import build_initialize_pool_ix
from ..core.constants import SOL_WRAPPED_MINT, TOKEN_PROGRAM_ID, TOKEN_PROGRAM_2022_ID, \
    LAMPORTS_PER_SOL, TOKEN_WITH_DECIMALS, MILLION

def _distribute_amount_simple(
    wallets: list[Wallet],
    target_amount: int,
    delta: float = 0.01,
    reserve_fee: int = int(0.1 * LAMPORTS_PER_SOL)
) -> list[tuple[Wallet, int]]:
    """
    Distribute lamports across wallets with small random deviation.
    If wallet can't pay full part, it pays max possible minus fee reserve.

    :param wallets: List of Wallet(address, lamports_balance)
    :param target_amount: Target amount in lamports
    :param delta: Deviation as percent of base (e.g. 0.01 = ±1%)
    :param reserve_fee: Fee to keep on wallet (in lamports)
    :return: List of (Wallet, lamports_to_pay)
    """
    N = len(wallets)
    base = target_amount // N

    parts = [
        int(base * (1 + random.uniform(-delta, delta)))
        for _ in range(N)
    ]

    total_parts = sum(parts)
    parts = [int(p * target_amount / total_parts) for p in parts]

    result = []
    for wallet, part in zip(wallets, parts):
        max_can_pay = max(wallet.lamports_balance - reserve_fee, 0)
        pay = min(part, max_can_pay)
        result.append((wallet, pay))

    return result

async def initialize_pool(
    solana_client: SolanaClient,
    token_amount_ui: int,
    wsol_amount_ui: float,
    dev_wallet: Wallet,
    sniper_wallets: list[Wallet],
    snipe_amount_ui: Optional[float],
    created_token_string: str,
    random_pool_id: Optional[Pubkey] = None,
    transfer_fee: int = 0
):
    if len(sniper_wallets) > 4:
        raise RuntimeError("Too much txs")

    token_amount = token_amount_ui * TOKEN_WITH_DECIMALS * MILLION
    wsol_amount = int(wsol_amount_ui * LAMPORTS_PER_SOL)
    created_token_mint = Pubkey.from_string(created_token_string)
    creator_pub = dev_wallet.pubkey

    token_ata = get_associated_token_address(
        owner=creator_pub,
        mint=created_token_mint,
        token_program_id=TOKEN_PROGRAM_2022_ID
    )
    wsol_ata = get_associated_token_address(
        owner=creator_pub,
        mint=SOL_WRAPPED_MINT,
    )
    create_wsol_ata_ix = create_idempotent_associated_token_account(
        payer=creator_pub,
        owner=creator_pub,
        mint=SOL_WRAPPED_MINT,
    )
    transfer_sol_ix = transfer(
        TransferParams(
            from_pubkey=creator_pub,
            to_pubkey=wsol_ata,
            lamports=wsol_amount,
        )
    )
    sync_native_ix = sync_native(
        SyncNativeParams(
            account=wsol_ata,
            program_id=TOKEN_PROGRAM_ID,
        )
    )

    tx_data = prepare_liquidity_pool_data(
        creator=dev_wallet.keypair,
        created_token_mint=created_token_mint,
        created_token_ata=token_ata,
        sol_ata=wsol_ata,
        random_pool_id=random_pool_id,
        token_amount=token_amount,
        wsol_amount=wsol_amount,
        transfer_fee=transfer_fee,
    )
    initialize_pool_ix = build_initialize_pool_ix(
        tx_data=tx_data,
        open_time_unix=int(time.time()),
    )

    ixs = [
        create_wsol_ata_ix,
        transfer_sol_ix,
        sync_native_ix,
        initialize_pool_ix,
    ]
    signers = [dev_wallet.keypair]

    if sniper_wallets:
        if not snipe_amount_ui:
            raise RuntimeError("You forgot snipe amount ui")

        balances = await solana_client.get_multiple_accounts_lamports_balances(
            [w.pubkey for w in sniper_wallets]
        )

        for w, b in zip(sniper_wallets, balances):
            w.lamports_balance = b

        '''print(await solana_client.simulate_transaction(
            instructions=ixs,
            msg_signer=dev_wallet.keypair,
            signers_keypairs=signers,
        ))'''

        initialize_pool_JITO_tx = await solana_client._build_raw_transaction_jito(
            instructions=ixs,
            msg_signer=dev_wallet.keypair,
            signers_keypairs=signers,
            priority_fee=20000,
            compute_limit=300_000,
            label="Initialize",
            jito_tip=3_000_000, # 0.003 SOL
        )
        buy_JITO_txs = []

        wallet_amounts_tup = _distribute_amount_simple(
            wallets=sniper_wallets,
            target_amount=snipe_amount_ui * LAMPORTS_PER_SOL,
        )

        for wlt, amt in wallet_amounts_tup:
            buy_ixs = await prepare_swap_base_in(
                wallet=wlt,
                amount=amt,
            )

            '''print(await solana_client.simulate_transaction(
                instructions=buy_ixs,
                msg_signer=wlt.keypair,
                signers_keypairs=[wlt.keypair],
            ))'''

            buy_JITO_txs.append(
                await solana_client._build_raw_transaction_jito(
                    instructions=buy_ixs,
                    msg_signer=wlt.keypair,
                    signers_keypairs=[wlt.keypair],
                    priority_fee=20000,
                    compute_limit=300_000,
                    label="BUY",
                )
            )
        try:
            await solana_client.send_jito_bundle_transactions(
                transactions=[initialize_pool_JITO_tx, *buy_JITO_txs],
            )
        except Exception as e:
            print(e)
    else:
        try:
            await solana_client.build_and_send_transaction(
                instructions=ixs,
                msg_signer=dev_wallet.keypair,
                signers_keypairs=signers,
                priority_fee=20000,
                compute_limit=300_000,
                max_retries=1,
                label="Initialize"
            )
        except Exception as e:
            print(e)


