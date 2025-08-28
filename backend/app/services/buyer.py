import random
import asyncio
import struct
from typing import Final
from dataclasses import dataclass

from solders.compute_budget import set_compute_unit_price
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.solders import Signature
from spl.token.instructions import get_associated_token_address, create_idempotent_associated_token_account
from ..core.constants import (
    PUMP_PROGRAM,
    PUMP_GLOBAL,
    PUMP_EVENT_AUTHORITY,
    PUMP_FEE,
    SYSTEM_PROGRAM,
    SYSTEM_TOKEN_PROGRAM,
    LAMPORTS_PER_SOL,
    SAVE_FEE_AMOUNT,
    SLIPPAGE,
    DECIMALS, TOKEN_PROGRAM_2022_ID,
)
from ..core.client import SolanaClient
from ..core.data_collector import DataCollector
from ..dto import TokenDTO, InitializeBuyTokensRequest
from ..core.wallet_manager import Wallet, WalletManager
from ..enums import Role
from ..core.logger import logger
from .tokens import get_token
from .creator import create_token_prepare_instruction
from .utils import _compute_random_amount_for_group

EXPECTED_DISCRIMINATOR: Final[bytes] = struct.pack("<Q", 16927863322537952870)

@dataclass(frozen=True, slots=True)
class Buyer:
    group: Role
    max_amount_lamports: int
    buy_tokens_amount: int
    keypair: Keypair

async def _calculate_req_lamports_for_buyer(
    *,
    wallet: Wallet,
    tokens_amount: int,
    dc: DataCollector,
    token_info: TokenDTO,
    init: bool = False,
) -> Buyer:
    token_amount_dec = int(tokens_amount * 10 ** DECIMALS)
    wallet_pub = wallet.pubkey
    lamports_total = int(wallet.lamports_balance)
    reserve = int(SAVE_FEE_AMOUNT * LAMPORTS_PER_SOL)
    lamports_available = max(lamports_total - reserve, 0)

    if lamports_available <= 0:
        logger.warning(f"Wallet {wallet_pub} has no spendable balance")

    if not init:
        bonding_curve: Pubkey = Pubkey.from_string(token_info.bonding_curve)
        price = await dc.get_price(bonding_curve)
        required_lamports = int(token_amount_dec * price * (1 + SLIPPAGE) * LAMPORTS_PER_SOL)

        if lamports_available < required_lamports:
            logger.warning(
                f"Not enough SOL in {wallet_pub}. Need {required_lamports}, available {lamports_available}"
            )

    return Buyer(
        group=wallet.group,
        keypair=wallet.keypair,
        buy_tokens_amount=token_amount_dec,
        max_amount_lamports=lamports_total,
    )

async def _calculate_req_tokens_for_buyer(
    *,
    wallet: Wallet,
    token_info: TokenDTO,
    dc: DataCollector,
    sol_amount: float,

) -> Buyer:
    wallet_pub = wallet.pubkey

    lamports_total = wallet.lamports_balance
    reserve = int(SAVE_FEE_AMOUNT * LAMPORTS_PER_SOL)
    lamports_available = max(lamports_total - reserve, 0)

    if lamports_available <= 0:
        logger.warning(f"Wallet {wallet_pub} has no spendable balance")

    required_lamports = int(sol_amount * (1 + SLIPPAGE) * LAMPORTS_PER_SOL)
    if lamports_available < required_lamports:
        logger.warning(
            f"Not enough SOL in {wallet_pub}. Need {required_lamports}, available {lamports_available}"
        )

    bonding_curve: Pubkey = Pubkey.from_string(token_info.bonding_curve)
    price = await dc.get_price(bonding_curve)

    sol_effective = sol_amount / (1 + SLIPPAGE)
    tokens_float = sol_effective / price
    tokens_amount = int(tokens_float * 10**DECIMALS)

    return Buyer(
        group=wallet.group,
        keypair=wallet.keypair,
        buy_tokens_amount=tokens_amount,
        max_amount_lamports=required_lamports,
    )

async def buy_token_prepare_instruction(
    *,
    token_info: TokenDTO,
    buyer: Buyer,
) -> Instruction:

    wallet_pub: Pubkey = buyer.keypair.pubkey()
    mint_address: Pubkey = Pubkey.from_string(token_info.mint_address)
    bonding_curve: Pubkey = Pubkey.from_string(token_info.bonding_curve)
    associated_bonding_curve: Pubkey = Pubkey.from_string(token_info.associated_bonding_curve)
    coin_creator_vault: Pubkey = Pubkey.from_string(token_info.token_creator_vault)
    ata_pk = get_associated_token_address(wallet_pub, mint_address)

    accounts = [
        AccountMeta(pubkey=PUMP_GLOBAL, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_FEE, is_signer=False, is_writable=True),
        AccountMeta(pubkey=mint_address, is_signer=False, is_writable=False),
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(pubkey=associated_bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(pubkey=ata_pk, is_signer=False, is_writable=True),
        AccountMeta(pubkey=wallet_pub, is_signer=True, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_TOKEN_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(pubkey=coin_creator_vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),
    ]

    logger.info(f"Packing buy_tokens_amount={buyer.buy_tokens_amount} max_amount_lamports={buyer.max_amount_lamports}")
    data = (
        EXPECTED_DISCRIMINATOR
        + struct.pack("<Q", buyer.buy_tokens_amount)
        + struct.pack("<Q", buyer.max_amount_lamports)
    )

    buy_ix = Instruction(
        program_id=PUMP_PROGRAM,
        data=data,
        accounts=accounts
    )

    return buy_ix

async def build_many_buy_instructions(
    buyers: list[Buyer],
    token_info: TokenDTO,
) -> tuple[list[Instruction], list[Keypair]]:

    instructions: list[Instruction] = []
    signers: list[Keypair] = []

    for buyer in buyers:
        ix = await buy_token_prepare_instruction(
            token_info=token_info,
            buyer=buyer,
        )
        instructions.append(ix)
        if buyer.keypair not in signers:
            signers.append(buyer.keypair)

    return instructions, signers

async def buy_token_initialize(
    client: SolanaClient,
    dev_buyer: Buyer,
    group_buyers: list[Buyer],
    token_info: TokenDTO,
) -> tuple[Signature, bool]:
    """
    Atomically buy tokens for dev + group wallets in one transaction.

    Parameters
    ----------
    client:
        Active AsyncClient connection.
    dev_buyer:
        Dev Keypair (acts as fee-payer).
    group_buyers:
        1-3 additional buyer Keypairs.
    token_info:
        SPL-token mint.
    Returns
    -------
    str
        Signature (base58) of the submitted transaction.

    Raises
    ------
    RuntimeError
        If message > 1 232 bytes or signers > 15.
    """
    buy_instructions, signers = await build_many_buy_instructions(
        buyers=[dev_buyer, *group_buyers],
        token_info=token_info,
    )
    return await client.build_and_send_transaction(
        instructions=buy_instructions,
        msg_signer=dev_buyer.keypair,
        signers_keypairs=signers,
    )


async def dev_buy_initialize(
    wm: WalletManager,
    dc: DataCollector,
    solana_client: SolanaClient,
    amounts: InitializeBuyTokensRequest,
) -> None:
    """
    Одной атомарной транзакцией:
      • делает buy от dev-кошелька и всех group1-кошельков.
    """
    ixs = []

    token_info: TokenDTO = await get_token()
    dev_wallet: Wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    dev_buyer: Buyer = await _calculate_req_lamports_for_buyer(
        wallet=dev_wallet,
        tokens_amount=amounts.dev,
        dc=dc,
        token_info=token_info,
        init=True,
    )

    ixs.append(await create_token_prepare_instruction(
        mint_info=token_info,
        dev=dev_wallet,
    ))
    ixs.append(create_idempotent_associated_token_account(
        payer=dev_wallet.pubkey,
        owner=dev_wallet.pubkey,
        mint=Pubkey.from_string(token_info.mint_address),
    ))

    signers = [Keypair.from_bytes(list(token_info.private_key))]

    group1_wallets: list[Wallet] = await wm.get_wallets_by_group(Role.group1)
    gr1_buyers: list[Buyer] = []
    for w in group1_wallets:
        amount = int(amounts.group1 / len(group1_wallets))
        buyer = await _calculate_req_lamports_for_buyer(
            wallet=w,
            tokens_amount=amount,
            dc=dc,
            token_info=token_info,
            init=True,
        )
        gr1_buyers.append(buyer)
        ixs.append(create_idempotent_associated_token_account(
            payer=w.pubkey,
            owner=w.pubkey,
            mint=Pubkey.from_string(token_info.mint_address),
        ))

    buy_instructions, sigs = await build_many_buy_instructions(
        buyers=[dev_buyer, *gr1_buyers],
        token_info=token_info,
    )
    ixs.extend(buy_instructions)
    signers.extend(sigs)
    try:
        await solana_client.build_and_send_transaction(
            instructions=ixs,
            msg_signer=dev_buyer.keypair,
            signers_keypairs=signers,
            label="DEV_BUY_INITIALIZE"
        )
    except Exception as e:
        logger.error(f"Failed to Sent DEV_BUY_INITIALIZE tx: {e}")

    await dc.update_lamports_balances([dev_wallet, *group1_wallets])

async def buy_group(
    solana_client: SolanaClient,
    wm: WalletManager,
    dc: DataCollector,
    group: Role,
    amount: float
):
    token_info: TokenDTO = await get_token()
    wallets: list[Wallet] = await wm.get_wallets_by_group(group)
    amounts: list[float] = await _compute_random_amount_for_group(
        length=len(wallets),
        amount=amount,
    )

    logger.info("💸 Buy plan (SOL):")
    for wallet, amount in zip(wallets, amounts):
        logger.info(f"{wallet.name[:6]}… → {amount:.4f} SOL")
        buyer: Buyer = await _calculate_req_tokens_for_buyer(
            wallet=wallet,
            sol_amount=amount,
            dc=dc,
            token_info=token_info,
        )

        buy_ix: Instruction = await buy_token_prepare_instruction(
            token_info=token_info,
            buyer=buyer,
        )
        try:
            await solana_client.build_and_send_transaction(
                instructions=[buy_ix],
                msg_signer=wallet.keypair,
                signers_keypairs=[wallet.keypair],
                max_confirm_retries=0,
            )
        except Exception as e:
            logger.error(f"❌ Failed for wallet {wallet.name[:6]}… — {e}")

        interval = random.randint(1, 3)/10
        await asyncio.sleep(interval)

    await dc.update_lamports_balances(wallets)
    logger.info(f"✅ Finished buy_group for {group.value}")
