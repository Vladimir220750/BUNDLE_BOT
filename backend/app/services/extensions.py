import struct
from solders.solders import Pubkey
from solders.keypair import Keypair
from dataclasses import dataclass
from typing import Optional

from solders.instruction import AccountMeta, Instruction

from ..core.client import SolanaClient
from ..core.logger import logger
from ..core.constants import LAMPORTS_PER_SOL, TOKEN_PROGRAM_2022_ID

PERCENT_FEE_BPS = 100

AUTHORITY_TYPE_INDEX = {
    "mintTokens": 0,
    "freezeAccount": 1,
    "accountOwner": 2,
    "closeAccount": 3,
    "transferFeeConfig": 4,
    "withheldWithdraw": 5,
    "closeMint": 6,
    "interestRate": 7,
    "permanentDelegate": 8,
    "confidentialTransferMint": 9,
    "transferHookProgramId": 10,
    "confidentialTransferFeeConfig": 11,
    "metadataPointer": 12,
    "groupPointer": 13,
    "groupMemberPointer": 14,
    "scaledUiAmount": 15,
    "pause": 16,
}

def _pack_set_authority_data(authority_type_name: str,
                             new_authority: Optional[Pubkey]) -> bytes:
    if authority_type_name not in AUTHORITY_TYPE_INDEX:
        raise ValueError(f"Unknown authorityType: {authority_type_name}")

    disc = 6  # SetAuthority
    at = AUTHORITY_TYPE_INDEX[authority_type_name]

    out = bytearray()
    out += struct.pack("<B", disc)         # discriminator (6)
    out += struct.pack("<B", at)           # authority_type index
    if new_authority is None:
        out += struct.pack("<B", 0)        # Option<Pubkey>::None
    else:
        out += struct.pack("<B", 1)        # Option<Pubkey>::Some
        out += bytes(new_authority)        # 32 bytes
    return bytes(out)

@dataclass
class TransferFee:
    epoch: int
    maximum_fee: int
    transfer_fee_bps: int

@dataclass
class TransferFeeState:
    newer_fee: TransferFee
    older_fee: TransferFee
    fee_authority: Optional[Pubkey]
    withdraw_authority: Optional[Pubkey]
    withheld_amount: int

    @classmethod
    def to_dict(cls):
        return {
            "newer_fee": {
                "epoch": cls.newer_fee.epoch,
                "maximum_fee_sol": cls.newer_fee.maximum_fee / LAMPORTS_PER_SOL,
                "transfer_fee": cls.newer_fee.transfer_fee_bps / PERCENT_FEE_BPS,
            },
            "older_fee": {
                "epoch": cls.older_fee.epoch,
                "maximum_fee_sol": cls.older_fee.maximum_fee / LAMPORTS_PER_SOL,
                "transfer_fee": cls.older_fee.transfer_fee_bps / PERCENT_FEE_BPS,
            },
            "fee_authority": str(cls.fee_authority),
            "withdraw_authority": str(cls.withdraw_authority),
            "withheld_amount": cls.withheld_amount
        }

TRANSFER_FEE_STATE: None | TransferFeeState = None

async def fetch_transfer_fee_config(
    solana_client: SolanaClient,
    mint: Pubkey
) -> dict | TransferFeeState:
    try:
        resp = await solana_client.get_account_info(mint, encoding="jsonParsed")
    except Exception as e:
        print(e)
        return {"error": "Error while getting account info"}

    info = resp.value.data.parsed.get("info", {})
    extensions = info.get("extensions", [])
    transfer_fee_extension = next(
        (ext for ext in extensions if ext["extension"] == "transferFeeConfig"),
        None
    )
    if transfer_fee_extension:
        fee_state = transfer_fee_extension["state"]
        newer_fee = fee_state["newerTransferFee"]
        older_fee = fee_state["olderTransferFee"]

        try:
            fee_authority = Pubkey.from_string(fee_state["transferFeeConfigAuthority"])
        except (TypeError, ValueError):
            fee_authority = None

        try:
            withdraw_authority = Pubkey.from_string(fee_state["withdrawWithheldAuthority"])
        except (TypeError, ValueError):
            withdraw_authority = None

        global TRANSFER_FEE_STATE
        TRANSFER_FEE_STATE = TransferFeeState(
            newer_fee=TransferFee(
                epoch=newer_fee.get("epoch", 0),
                maximum_fee=newer_fee.get("maximum_fee", 100000000000000000),
                transfer_fee_bps=newer_fee.get("transfer_fee_bps", 1000),
            ),
            older_fee=TransferFee(
                epoch=older_fee.get("epoch", 0),
                maximum_fee=older_fee.get("maximum_fee", 100000000000000000),
                transfer_fee_bps=older_fee.get("transfer_fee_bps", 1000),
            ),
            fee_authority=fee_authority,
            withdraw_authority=withdraw_authority,
            withheld_amount=fee_state["withheldAmount"]
        )

        return TRANSFER_FEE_STATE
    return {"error": "Extension not found"}

def build_set_authority_ix(
    *,
    mint: Pubkey, # mint_address
    current_authority: Pubkey, # current authority
    authority_type: str,
    new_authority: Optional[Pubkey],
    program_id: Pubkey,
) -> Instruction:

    data = _pack_set_authority_data(authority_type, new_authority)
    accounts = [
        AccountMeta(pubkey=mint,              is_signer=False, is_writable=True),
        AccountMeta(pubkey=current_authority, is_signer=True,  is_writable=False),
    ]

    return Instruction(program_id=program_id, accounts=accounts, data=data)

def build_set_transfer_fee_ix():
    pass

async def change_transfer_fee_config(
    solana_client: SolanaClient,
    config: dict,
):
    pass


async def set_withdraw_authority(
    solana_client: SolanaClient,
    new_kp: Keypair,
    old_kp: Keypair,
    mint: Pubkey,
):
    ix = build_set_authority_ix(
        mint=mint,
        current_authority=old_kp.pubkey(),
        new_authority=new_kp.pubkey(),
        program_id=TOKEN_PROGRAM_2022_ID,
        authority_type="withheldWithdraw"
    )

    try:
        sig, success = await solana_client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=new_kp,
            signers_keypairs=[new_kp, old_kp],
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=50000
        )
        logger.info(f"setting withdraw authority Success: {success}, tx: https://solscan.io/tx/{sig}")
    except Exception as e:
        logger.error(f"Error while setting withdraw authority")
        raise