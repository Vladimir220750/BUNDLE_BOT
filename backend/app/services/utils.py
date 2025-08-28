import httpx
import json
import random
import struct
from typing import Final, Any

from construct import Struct, Int32ul, Bytes, this
from base64 import b64decode
from solders.pubkey import Pubkey
from solders.solders import Instruction, AccountMeta

from ..dto import CONFIGDTO
from ..core.config import settings
from ..core.constants import (
    PUMP_PROGRAM,
    SYSTEM_TOKEN_PROGRAM,
    SYSTEM_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM,
    MPL_TOKEN_METADATA_ID
)
from ..core.logger import logger

EXPECTED_DISCRIMINATOR: Final[bytes] = struct.pack("<Q", 8576854823835016728)

CreateArgs = Struct(
    "name" / Struct(
        "length" / Int32ul,
        "chars" / Bytes(this.length)
    ),
    "symbol" / Struct(
        "length" / Int32ul,
        "chars" / Bytes(this.length)
    ),
    "uri" / Struct(
        "length" / Int32ul,
        "chars" / Bytes(this.length)
    ),
    "creator" / Bytes(32)
)

def pack_create_data(name: str, symbol: str, uri: str, creator: Pubkey) -> bytes:
    return (
        EXPECTED_DISCRIMINATOR +
        CreateArgs.build({
            "name": {
                "length": len(name.encode()),
                "chars": name.encode()
            },
            "symbol": {
                "length": len(symbol.encode()),
                "chars": symbol.encode()
            },
            "uri": {
                "length": len(uri.encode()),
                "chars": uri.encode()
            },
            "creator": bytes(creator)
        })
    )

async def get_coin_creator_vault(coin_creator: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(
        [
            b"creator-vault",
            bytes(coin_creator)
        ],
        PUMP_PROGRAM,
    )

async def get_mint_authority() -> Pubkey:
    return Pubkey.find_program_address([b"mint-authority"], PUMP_PROGRAM)

async def get_metadata(mint: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(
    [b"metadata", bytes(MPL_TOKEN_METADATA_ID), bytes(mint)],
    MPL_TOKEN_METADATA_ID
)

async def get_bonding_curve_address(mint: Pubkey) -> tuple[Pubkey, int]:
    """
    Derives the bonding curve address for a given mint
    """
    return Pubkey.find_program_address([b"bonding-curve", bytes(mint)], PUMP_PROGRAM)


async def find_associated_bonding_curve(mint: Pubkey, bonding_curve: Pubkey) -> Pubkey:
    """
    Find the associated bonding curve for a given mint and bonding curve.
    This uses the standard ATA derivation.
    """

    derived_address, _ = Pubkey.find_program_address(
        [
            bytes(bonding_curve),
            bytes(SYSTEM_TOKEN_PROGRAM),
            bytes(mint),
        ],
        SYSTEM_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM,
    )
    return derived_address

async def derive_bonding_accounts(mint: Pubkey):
    bonding_curve, _ = await get_bonding_curve_address(mint)
    derived_address = await find_associated_bonding_curve(mint, bonding_curve)
    return bonding_curve, derived_address


async def _create_raw_metadata(
    name: str,
    symbol: str,
    description: str,
    uri: str,
    telegram: str,
    twitter: str,
    website: str,
) -> dict:
    return {
        "name": name,
        "symbol": symbol,
        "description": description,
        "image": uri,
        "showName": True,
        "createdOn": "https://pump.fun",
        "twitter": twitter,
        "telegram": telegram,
        "website": website,
    }

async def _create_raw_metadata_raydium(
    name: str,
    symbol: str,
    description: str,
    uri: str,
    website: str,
    twitter: str,
    telegram: str,
) -> dict:
    return {
    "name": name,
      "symbol": symbol,
      "image": uri,
      "description": description,
      "website": website,
      "twitter": twitter,
      "telegram": telegram,
      "showName": True,
      "extensions": {
        "website": website,
        "twitter": twitter,
        "telegram": telegram
      },
      "tags": [],
      "createdOn": "https://revshare.dev",
      "createdOnName": "RevShare"
    }

async def _compute_random_amount_for_group(
    *,
    length: int,
    amount: float,
) -> list[float]:

    weights = []
    for _ in range(length):
        weight = random.uniform(0.2, 1.8)  # ±80%
        weights.append(weight)

    total_weight = 0.0
    for w in weights:
        total_weight += w

    parts: list[float] = []
    for weight in weights:
        part = round(amount * weight / total_weight, 6)
        parts.append(part)

    return parts

def load_config() -> CONFIGDTO:
    tmp_dir = settings.tmp_dir
    config_name = "config.json"
    with open(tmp_dir / config_name, "r") as f:
        config = json.load(f)

    return CONFIGDTO(**config)

def save_config(data: CONFIGDTO) -> None:
    tmp_dir = settings.tmp_dir
    config_name = "config.json"
    with open(tmp_dir / config_name, "w") as f:
        json.dump(data.model_dump(), f, indent=2, ensure_ascii=False)

def instruction_from_dict(d: dict) -> Instruction:
    return Instruction(
        program_id=Pubkey.from_string(d["program_id"]),
        accounts=[
            AccountMeta(
                pubkey=Pubkey.from_string(a["pubkey"]),
                is_signer=a["is_signer"],
                is_writable=a["is_writable"]
            )
            for a in d["accounts"]
        ],
        data=b64decode(d["data"]),
    )

async def get_external_ix(params: Any) -> list[Instruction]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{settings.raydium_backend}/instructions/swap_base_input/", json=params.model_dump())
            return [instruction_from_dict(d) for d in resp.json()]
    except Exception as e:
        logger.exception(f"Error while collecting Wallets: {e}")
        return []