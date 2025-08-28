import io
import json
from pathlib import Path

import base64
from fastapi import UploadFile
from fastapi.responses import JSONResponse
import httpx
from solders.solders import Keypair, Pubkey, Instruction
from spl.token.instructions import initialize_mint, InitializeMintParams, create_associated_token_account
from spl.token.instructions import mint_to_checked, MintToCheckedParams, set_authority, SetAuthorityParams, AuthorityType

from .creator import create_token_prepare_instruction
from ..core.client import SolanaClient
from ..core.config import settings
from ..core.constants import (
    PINATA_API_KEY,
    UPLOAD_FILE_ENDPOINT,
    PINATA_UPLOADED_URI,
    TOKEN_DECIMALS,
    TOKEN_PROGRAM_2022_ID,
    TOKEN_WITH_DECIMALS,

)
from ..core.wallet_manager import WalletManager
from ..dto import TokenDTO, TokenCreateRequest, Role, CreateTokenRaydiumRequest, RaydiumTokenDTO, CopyTokenResponse
from .utils import _create_raw_metadata, derive_bonding_accounts, get_coin_creator_vault, get_metadata, _create_raw_metadata_raydium
from ..core.logger import logger
from .mint import build_create_mint_account_ix, build_initialize_mint_ix
from .transfers import build_initialize_transfer_fee_config_ix
from .token_metadata import build_initialize_metadata_pointer_ix, build_initialize_token_metadata_ix

TOKENS_DIR = Path("/data/tokens")
TOKENS_DIR.mkdir(parents=True, exist_ok=True)

MAX_TRANSFER_FEE_AMOUNT = 1_000_000_000

async def _upload_file_to_pinata(
    upload_file: UploadFile,
    filename: str,
    content_type: str = ""
) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        files = {
            "file": (filename, upload_file.file, content_type or "application/octet-stream"),
            "network": (None, "public")
        }
        headers = {"Authorization": f"Bearer {PINATA_API_KEY}"}
        response = await client.post(UPLOAD_FILE_ENDPOINT, files=files, headers=headers)
        response.raise_for_status()
        cid = response.json()["data"]["cid"]
        return PINATA_UPLOADED_URI.format(cid=cid)

async def prepare_token(
    data: TokenCreateRequest,
    wm: WalletManager,
) -> TokenDTO:
    img_uri: str = await _upload_file_to_pinata(
        data.image,
        data.image.filename
    )

    print(data)

    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    meta = await _create_raw_metadata(
        name=data.name,
        symbol=data.symbol,
        description=data.description,
        uri=img_uri,
        telegram=data.telegram,
        website=data.website,
        twitter=data.twitter,
    )

    metadata_json = json.dumps(meta, separators=(",", ":")).encode()
    json_file = io.BytesIO(metadata_json)
    json_file.name = "metadata.json"
    upload_meta = UploadFile(
        filename="metadata.json",
        file=json_file,
    )

    metadata_uri: str = await _upload_file_to_pinata(
        upload_meta,
        "metadata.json",
        content_type="application/json",
    )

    mint_kp = Keypair()
    mint_pub = mint_kp.pubkey()
    bonding_curve, ass_bonding_curve = await derive_bonding_accounts(mint_pub)
    token_creator_vault, _ = await get_coin_creator_vault(dev_wallet.pubkey)
    metadata, _ = await get_metadata(mint_pub)

    token = TokenDTO(
            name=data.name,
            symbol=data.symbol,
            uri=metadata_uri,
            mint_address=str(mint_pub),
            bonding_curve=str(bonding_curve),
            private_key=list(mint_kp.to_bytes()),
            associated_bonding_curve=str(ass_bonding_curve),
            token_creator_vault=str(token_creator_vault),
            metadata=str(metadata),
    )

    await save_token(token)
    logger.info(f"IMAGE: {img_uri}, META: {metadata_uri}")
    return token

async def prepare_token_raydium(
    data: CreateTokenRaydiumRequest,
) -> str:

    if data.supply <= 0:
        raise RuntimeError(f"You forgot SUPPLY")

    img_uri: str = await _upload_file_to_pinata(
        data.image,
        data.image.filename
    )

    meta = await _create_raw_metadata_raydium(
        name=data.name,
        symbol=data.symbol,
        description=data.description,
        uri=img_uri,
        website=data.website,
        telegram=data.telegram,
        twitter=data.twitter,
    )

    metadata_json = json.dumps(meta, separators=(",", ":")).encode()
    json_file = io.BytesIO(metadata_json)
    json_file.name = "metadata.json"
    upload_meta = UploadFile(
        filename="metadata.json",
        file=json_file,
    )

    metadata_uri: str = await _upload_file_to_pinata(
        upload_meta,
        "metadata.json",
        content_type="application/json",
    )

    mint_kp = Keypair()
    transfer_fee_authority_kp = Keypair()
    mint_pub = mint_kp.pubkey()

    token = RaydiumTokenDTO(
        name=data.name,
        symbol=data.symbol,
        uri=metadata_uri,
        mint_address=str(mint_pub),
        private_key=list(mint_kp.to_bytes()),
        transfer_fee_authority_kp=list(transfer_fee_authority_kp.to_bytes()),
        tax=data.tax * 100, # in basis points
        supply=data.supply * 1_000_000,
        mint_authority=data.mint_authority,
        freeze_authority=data.freeze_authority,
    )

    await save_token(token, token_file="token_raydium.json")
    logger.info(f"IMAGE: {img_uri}, META: {metadata_uri}")
    return str(mint_pub)

async def update_token_from_pumpfun(
    mint_address: str,
    wm: WalletManager,
):
    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    token_info = await get_token()

    try:
        mint_pub = Pubkey.from_string(mint_address)
    except ValueError:
        logger.error(f"mint_address incorrect: {mint_address}")
        return

    bonding_curve, ass_bonding_curve = await derive_bonding_accounts(mint_pub)
    token_creator_vault, _ = await get_coin_creator_vault(dev_wallet.pubkey)

    token_info.mint_address = str(mint_pub)
    token_info.token_creator_vault = str(token_creator_vault)
    token_info.bonding_curve = str(bonding_curve)
    token_info.associated_bonding_curve = str(ass_bonding_curve)

    await save_token(token_info)

async def create_token(
    solana_client: SolanaClient,
    wm: WalletManager,
):
    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    token_info = await get_token()
    mint_kp = Keypair.from_bytes(bytes(token_info.private_key))
    create_ix = await create_token_prepare_instruction(
        mint_info=token_info,
        dev=dev_wallet,
    )
    try:
        await solana_client.build_and_send_transaction(
            instructions=[create_ix],
            msg_signer=dev_wallet.keypair,
            signers_keypairs=[mint_kp, dev_wallet.keypair],
            label="CREATE_TOKEN"
        )
    except Exception as e:
        logger.error(f"Failed to Sent CREATE_TOKEN tx: {e}")

async def create_token_raydium(
    solana_client: SolanaClient,
    wm: WalletManager,
):
    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    group1_w = (await wm.get_wallets_by_group(Role.group1))[0]
    token_info: RaydiumTokenDTO = await get_token("token_raydium.json")
    mint_kp = Keypair.from_bytes(bytes(token_info.private_key))
    mint_pub = Pubkey.from_string(token_info.mint_address)

    ixs: list[Instruction] = [await build_create_mint_account_ix(
        payer=dev_wallet.pubkey,
        mint=mint_pub,
        solana_client=solana_client,
    )]
    ixs.append(build_initialize_transfer_fee_config_ix(
            mint=mint_pub,
            authority=group1_w.pubkey,
            basis_points=token_info.tax,
            max_fee=MAX_TRANSFER_FEE_AMOUNT * 10 ** TOKEN_DECIMALS,
    ))
    ixs.append(build_initialize_metadata_pointer_ix(
        mint=mint_pub,
        authority=dev_wallet.pubkey,
        metadata_address=mint_pub
    ))
    ixs.append(build_initialize_mint_ix(
        decimals=TOKEN_DECIMALS,
        mint=mint_pub,
        mint_authority=dev_wallet.pubkey,
        freeze_authority=dev_wallet.pubkey,
    ))
    ixs.append(build_initialize_token_metadata_ix(
        metadata=mint_pub,
        update_authority=dev_wallet.pubkey,
        mint=mint_pub,
        mint_authority=dev_wallet.pubkey,
        name=token_info.name,
        symbol=token_info.symbol,
        uri=token_info.uri,
    ))
    ixs.append(create_associated_token_account(
        payer=dev_wallet.pubkey,
        owner=dev_wallet.pubkey,
        mint=mint_pub,
        token_program_id=TOKEN_PROGRAM_2022_ID,
    ))
    ixs.append(mint_to_checked(
        MintToCheckedParams(
            program_id=TOKEN_PROGRAM_2022_ID,
            mint=mint_pub,
            dest=dev_wallet.get_ata(mint=mint_pub, token_program=TOKEN_PROGRAM_2022_ID),
            mint_authority=dev_wallet.pubkey,
            amount=token_info.supply * TOKEN_WITH_DECIMALS,
            decimals=TOKEN_DECIMALS,
        )
    ))

    if  not token_info.mint_authority:
        ixs.append(set_authority(
            SetAuthorityParams(
                program_id=TOKEN_PROGRAM_2022_ID,
                account=mint_pub,
                authority=AuthorityType.MINT_TOKENS,
                current_authority=dev_wallet.pubkey,
                new_authority=None,
            )
        ))
    if not token_info.freeze_authority:
        ixs.append(set_authority(
            SetAuthorityParams(
                program_id=TOKEN_PROGRAM_2022_ID,
                account=mint_pub,
                authority=AuthorityType.FREEZE_ACCOUNT,
                current_authority=dev_wallet.pubkey,
                new_authority=None,
            )
        ))

    try:
        await solana_client.build_and_send_transaction(
            instructions=ixs,
            msg_signer=dev_wallet.keypair,
            signers_keypairs=[mint_kp, dev_wallet.keypair],
            label="CREATE RAYDIUM TOKEN",
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=20000,
        )
    except Exception as e:
        logger.error(f"Failed to Sent CREATE_TOKEN tx: {e}")

async def save_token(data: TokenDTO | RaydiumTokenDTO, token_file: str = "token.json") -> dict:
    path = TOKENS_DIR / token_file
    payload = {**data.model_dump()}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return {"status": "ok", "path": str(path)}

async def get_token(token_file: str = "token.json") -> TokenDTO | RaydiumTokenDTO | None:
    path = TOKENS_DIR / token_file
    if not path.exists():
        return None
    with open(path) as f:
        raw = json.load(f)
        try:
            return TokenDTO(**raw)
        except Exception:
            return RaydiumTokenDTO(**raw)


async def copy_token(mint: str):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                follow_redirects=True,
                url=settings.helius_rpc_url,
                headers={'Content-Type': 'application/json'},
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "getAsset",
                    "params": {"id": mint}
                }
            )
            print(resp)
            resp.raise_for_status()
            result = resp.json().get('result', {})
            json_uri = result.get('content', {}).get('json_uri')

            metadata_resp = await client.get(url=json_uri)
            metadata_resp.raise_for_status()
            meta = metadata_resp.json()

            image_url = meta.get('image')
            image_b64 = None

            if image_url:
                image_resp = await client.get(image_url)
                if image_resp.status_code == 200:
                    image_b64 = base64.b64encode(image_resp.content).decode()

            return JSONResponse(content={
                "name": meta.get("name"),
                "symbol": meta.get("symbol"),
                "description": meta.get("description"),
                "telegram": meta.get("telegram"),
                "twitter": meta.get("twitter"),
                "website": meta.get("website"),
                "image": image_url,
                "image_base64": image_b64
            })

        except Exception as e:
            logger.error(f"Error while parsing metadata of token: {e}")
            return JSONResponse(content={"error": "Metadata parse error"}, status_code=500)
