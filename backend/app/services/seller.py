import struct
from typing import Optional
from dataclasses import dataclass
from solana.rpc.async_api import AsyncClient
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address
from .curve_state import get_pump_curve_state, calculate_pump_curve_price

from ..core.constants import (
    PUMP_GLOBAL,
    PUMP_FEE,
    SYSTEM_PROGRAM,
    SYSTEM_TOKEN_PROGRAM,
    PUMP_EVENT_AUTHORITY,
    PUMP_PROGRAM,
    DECIMALS,
    LAMPORTS_PER_SOL,
    SLIPPAGE,
)
from ..core.data_collector import DataCollector
from ..core.wallet_manager import Wallet, WalletManager
from ..dto import TokenDTO
from ..enums import Role
from ..core.logger import logger
from ..core.client import SolanaClient
from .tokens import get_token
from ..core.constants import MAX_INSTRUCTIONS_PER_TX

EXPECTED_DISCRIMINATOR = struct.pack("<Q", 6966180631402821399)

@dataclass(frozen=True, slots=True)
class Seller:
    group: Role
    min_amount_lamports: int
    sell_tokens_amount: int
    keypair: Keypair

async def _calculate_budget_for_seller(
    *,
    wallet: Wallet,
    token_info: TokenDTO,
    dc: DataCollector,
    tokens_percent: float,
) -> Seller:

    tokens = await dc.get_token_balance(wallet)
    if tokens <= 0:
        raise RuntimeError(f"Wallet {wallet.pubkey} has no spendable balance, STOPING")

    tokens_amount = int(tokens * (tokens_percent / 100))
    bonding_curve: Pubkey = Pubkey.from_string(token_info.bonding_curve)
    price = await dc.get_price(bonding_curve)
    token_amount_dec = tokens_amount / 10**DECIMALS

    min_sol_output = float(token_amount_dec) * float(price)
    slippage_factor = 1 - SLIPPAGE
    min_sol_output = int((min_sol_output * slippage_factor) * LAMPORTS_PER_SOL)

    return Seller(
        group=wallet.group,
        keypair=wallet.keypair,
        sell_tokens_amount=tokens_amount,
        min_amount_lamports=min_sol_output,
    )

async def _calculate_req_tokens_for_seller(
    *,
    wallet: Wallet,
    token_info: TokenDTO,
    dc: DataCollector,
    sol_amount: float,
) -> Seller:

    wallet_pub = wallet.pubkey
    bonding_curve = Pubkey.from_string(token_info.bonding_curve)

    price = await dc.get_price(bonding_curve)
    if price <= 0:
        raise RuntimeError("Collector вернул не-положительную цену")

    tokens_float_need = (sol_amount / price) * (1 + SLIPPAGE)
    tokens_dec_need   = int(tokens_float_need * 10 ** DECIMALS)

    tokens = await dc.get_token_balance(wallet)
    if tokens <= 0:
        raise RuntimeError(f"Wallet {wallet_pub} has no spendable balance, STOPING")

    tokens_total_dec = int(tokens)
    if tokens_total_dec < tokens_dec_need:
        logger.warning(
            f"[SELL] {wallet_pub}: need {tokens_dec_need} tokens, "
            f"only {tokens_total_dec} available — selling all."
        )
        tokens_dec_need = tokens_total_dec

    min_sol_output = sol_amount * (1 - SLIPPAGE)
    min_amount_lamports = int(min_sol_output * LAMPORTS_PER_SOL)

    return Seller(
        group=wallet.group,
        keypair=wallet.keypair,
        sell_tokens_amount=tokens_dec_need,
        min_amount_lamports=min_amount_lamports,
    )

async def sell_token_prepare_instruction(
    *,
    token_info: TokenDTO,
    seller: Seller,
) -> Instruction:

    mint: Pubkey = Pubkey.from_string(token_info.mint_address)
    bonding_curve: Pubkey = Pubkey.from_string(token_info.bonding_curve)
    associated_bonding_curve: Pubkey = Pubkey.from_string(token_info.associated_bonding_curve)
    creator_vault: Pubkey = Pubkey.from_string(token_info.token_creator_vault)
    wallet_pub: Pubkey = seller.keypair.pubkey()
    associated_token_account: Pubkey = get_associated_token_address(wallet_pub, mint)

    accounts = [
        AccountMeta(pubkey=PUMP_GLOBAL, is_signer=False, is_writable=False),  # global False False
        AccountMeta(pubkey=PUMP_FEE, is_signer=False, is_writable=True),  # FEE False, True
        AccountMeta(pubkey=mint, is_signer=False, is_writable=False),  # mint False, False
        AccountMeta(pubkey=bonding_curve, is_signer=False, is_writable=True),  # bonding_curve False, True
        AccountMeta(pubkey=associated_bonding_curve, is_signer=False, is_writable=True),# associated_bonding_curve False, True
        AccountMeta(pubkey=associated_token_account, is_signer=False, is_writable=True),  # associated_user False, True
        AccountMeta(pubkey=wallet_pub, is_signer=True, is_writable=True),  # user True, True
        AccountMeta(pubkey=SYSTEM_PROGRAM, is_signer=False, is_writable=False),  # system_program False, False
        AccountMeta(pubkey=creator_vault, is_signer=False, is_writable=True),  # creator_vault False, True
        AccountMeta(pubkey=SYSTEM_TOKEN_PROGRAM, is_signer=False, is_writable=False),  # token_program False, False
        AccountMeta(pubkey=PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),  # event authority False, False
        AccountMeta(pubkey=PUMP_PROGRAM, is_signer=False, is_writable=False),  # program False, False
    ]

    discriminator = struct.pack("<Q", 12502976635542562355)
    data = (
            discriminator
            + struct.pack("<Q", seller.sell_tokens_amount)
            + struct.pack("<Q", seller.min_amount_lamports)
    )
    sell_ix = Instruction(PUMP_PROGRAM, data, accounts)

    return sell_ix

async def sell_wallet_batch(
    solana_client: SolanaClient,
    wallets: list[Wallet],
    dc: DataCollector,
    percent: float,
    max_per_tx: int,
) -> None:
    token_info: TokenDTO = await get_token()
    instructions: list[Instruction] = []
    signers: list[Keypair] = []

    for wallet in wallets:
        try:
            seller = await _calculate_budget_for_seller(
                wallet=wallet,
                token_info=token_info,
                dc=dc,
                tokens_percent=percent,
            )
        except RuntimeError as e:
            logger.error(f"SELL BUDGET CALCULATING ERROR - SKIP: {e}")
            continue

        ix = await sell_token_prepare_instruction(
            token_info=token_info,
            seller=seller,
        )
        instructions.append(ix)
        signers.append(wallet.keypair)

    for i in range(0, len(instructions), max_per_tx):
        signers_batch = signers[i:i + max_per_tx]
        try:
            await solana_client.build_and_send_transaction(
                instructions=instructions[i:i + max_per_tx],
                msg_signer=signers_batch[0],
                signers_keypairs=signers_batch,
                max_confirm_retries=0,
                max_retries=3,
                priority_fee=10_000,
            )
        except Exception as e:
            logger.error(f"Failed to send panic-sell tx: {e}")

async def sell_wallet_group(
    solana_client: SolanaClient,
    group: Role,
    wm: WalletManager,
    dc: DataCollector,
    percent: Optional[float] = 100,
    max_per_tx: int = MAX_INSTRUCTIONS_PER_TX,
) -> None:
    wallets = await wm.get_wallets_by_group(group)
    await sell_wallet_batch(
        solana_client=solana_client,
        wallets=wallets,
        dc=dc,
        percent=percent,
        max_per_tx=max_per_tx,
    )

async def panic_sell(
    solana_client: SolanaClient,
    wm: WalletManager,
    dc: DataCollector,
    percent: Optional[float] = 100,
    max_per_tx: int = MAX_INSTRUCTIONS_PER_TX,
) -> None:
    wallets = [w for w in wm.wallets if w.group != Role.fund]
    await sell_wallet_batch(
        solana_client=solana_client,
        wallets=wallets,
        dc=dc,
        percent=percent,
        max_per_tx=max_per_tx,
    )