from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.responses import FileResponse
from base58 import b58encode
from solders.solders import Pubkey, initialize_nonce_account
from solders.keypair import Keypair

from ..core.wallet_manager import WalletManager, Wallet
from ..core.data_collector import DataCollector
from ..services import buyer, key_pair, tokens, seller, profit_generator, utils, mint, transfers, extensions
from ..dto import (
    WalletsCreateRequest,
    GroupBuyRequest,
    GroupSellRequest,
    WalletDTO,
    DistributeRequest,
    TokenCreateRequest,
    InitializeBuyTokensRequest,
    UpdateTokenRequest,
    VolumeStartRequest,
    ArchiveWalletRequest,
    CONFIGDTO,
    WitdrawFeeRequest,
    MintToRequest,
    CreateTokenRaydiumRequest,
    UpdateTransferFeeConfigRequest,
    HideSupplyRequest,
SetWithdrawAuthorityRequest
)
from ..enums import Role
from ..deps.solana_client import get_solana_client
from ..deps.wallet_manager import get_wm
from ..deps.data_collector import get_dc
from ..core.client import SolanaClient
from ..deps.network import check_internal_host
from ..deps.volume_bot import get_volume_bot
from ..core.volume_bot import VolumeBot, VolumeBotConfig

router = APIRouter()

@router.post("/wallets/create/")
async def api_wallets_create(
    req: WalletsCreateRequest,
    wm: WalletManager = Depends(get_wm)
) -> list[WalletDTO]:
    return await wm.create_wallets(
        dev=req.dev,
        fund=req.fund,
        group1=req.group1,
        group2=req.group2,
    )

@router.get("/wallets/list/")
async def api_wallets_list(wm: WalletManager = Depends(get_wm)):
    return await wm.list_wallets_dto()

@router.get("/wallets/reload/")
async def api_wallets_list(wm: WalletManager = Depends(get_wm)):
    wm.load_wallets()

@router.post("/wallets/archive/")
async def archive_wallet(
    data: ArchiveWalletRequest,
    wm: WalletManager = Depends(get_wm)
):
    wm.archive_wallet_by_pubkey(Pubkey.from_string(data.wallet_pub))
    return await wm.list_wallets_dto()

@router.post("/buy/dev/")
async def api_buy_dev(
    data: InitializeBuyTokensRequest,
    dc: DataCollector = Depends(get_dc),
    wm: WalletManager = Depends(get_wm),
    client: SolanaClient = Depends(get_solana_client)
):
    await buyer.dev_buy_initialize(
        dc=dc,
        wm=wm,
        solana_client=client,
        amounts=data,
    )
    return {"status": "sent"}

@router.post("/buy/group/")
async def api_buy_group(
    data: GroupBuyRequest,
    solana_client: SolanaClient = Depends(get_solana_client),
    dc: DataCollector = Depends(get_dc),
    wm: WalletManager = Depends(get_wm)
):
    return await buyer.buy_group(
        solana_client=solana_client,
        group=data.group,
        amount=data.amount,
        dc=dc,
        wm=wm,
    )

@router.post("/sell/group/")
async def api_sell_group(
    data: GroupSellRequest,
    solana_client: SolanaClient = Depends(get_solana_client),
    dc: DataCollector = Depends(get_dc),
    wm: WalletManager = Depends(get_wm)
):
    return await seller.sell_wallet_group(
        solana_client=solana_client,
        group=data.group,
        percent=data.percent,
        dc=dc,
        wm=wm,
    )

@router.post("/sell/all/")
async def api_sell_all(
    client: SolanaClient = Depends(get_solana_client),
    dc: DataCollector = Depends(get_dc),
    wm: WalletManager = Depends(get_wm),
):
    return await seller.panic_sell(
        solana_client=client,
        dc=dc,
        wm=wm,
    )

@router.post("/distribute/")
async def api_distribute(
    data: DistributeRequest,
    wm: WalletManager = Depends(get_wm),
):
    """
    Distribute SOL from the fund wallet through 3 temporary hops
    to every destination specified in `data.transfers`.
    """
    return await wm.distribute_via_chain(data.transfers)

@router.post("/withdraw-to-fund/")
async def api_withdraw(
    wm: WalletManager = Depends(get_wm)
):
    return await wm.withdraw_to_fund()

@router.get("/wallets/private_key/{pubkey}/")
async def get_private_key_base58(pubkey: str):
    try:
        kp = key_pair.load_keypair_by_pubkey(pubkey)
        base58_key = b58encode(kp.to_bytes()).decode()
        return {"base58": base58_key}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Wallet not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("/prepare-token/")
async def prepare_token(
    name: str = Form(...),
    symbol: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...),
    telegram: str = Form(...),
    twitter: str = Form(...),
    website: str = Form(...),
    wm: WalletManager = Depends(get_wm)
):
    data = TokenCreateRequest(
        name=name,
        symbol=symbol,
        description=description,
        image=image,
        telegram=telegram,
        website=website,
        twitter=twitter,
    )
    return await tokens.prepare_token(
        data,
        wm=wm,
    )

@router.post("/create-token/")
async def create_token(
    wm: WalletManager = Depends(get_wm),
    solana_client: SolanaClient = Depends(get_solana_client),
):
    return await tokens.create_token(
        solana_client=solana_client,
        wm=wm,
    )

@router.post("/create-token-raydium/")
async def create_token_raydium(
    wm: WalletManager = Depends(get_wm),
    solana_client: SolanaClient = Depends(get_solana_client),
):
    return await tokens.create_token_raydium(
        solana_client=solana_client,
        wm=wm,
    )

@router.get("/copy-token/{address}/")
async def copy_token(
    address: str
):
    return await tokens.copy_token(
        mint=address
    )

@router.post("/prepare-token-raydium/")
async def prepare_token_raydium(
    name: str = Form(...),
    symbol: str = Form(...),
    description: str = Form(...),
    supply: int = Form(...),
    tax: int = Form(...),
    freeze_authority: bool = Form(...),
    mint_authority: bool = Form(...),
    telegram: str = Form(...),
    twitter: str = Form(...),
    website: str = Form(...),
    image: UploadFile = File(...),
):
    data = CreateTokenRaydiumRequest(
        name=name,
        symbol=symbol,
        description=description,
        supply=supply,
        tax=tax,
        freeze_authority=freeze_authority,
        mint_authority=mint_authority,
        telegram=telegram,
        twitter=twitter,
        website=website,
        image=image
    )

    return await tokens.prepare_token_raydium(
        data=data,
    )

@router.post("/update-token/")
async def update_token(
    data: UpdateTokenRequest,
    wm: WalletManager = Depends(get_wm),
):
    await tokens.update_token_from_pumpfun(mint_address=data.mint, wm=wm)

@router.get("/token/")
async def get_token():
    token = await tokens.get_token()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token

@router.post("/create-all-ata/")
async def create_all_ata(
    wm: WalletManager = Depends(get_wm),
    dc: DataCollector = Depends(get_dc),
):
    token = await tokens.get_token()
    mint = Pubkey.from_string(token.mint_address)
    wallets = [w for w in wm.wallets if w.group != Role.fund]
    await dc.update_token_balances(wallets=wallets)
    return await wm.create_ata_accounts(wallets, mint)

@router.post("/close-all-ata/")
async def close_all_ata(
    wm: WalletManager = Depends(get_wm)
):
    return await wm.close_all_ata_accounts()

@router.get("/export-wallets/")
async def export_wallets(
    wm: WalletManager = Depends(get_wm)
):
    wallets = wm.wallets
    to_export = [w.to_export() for w in wallets]
    return {
        "wallets": to_export,
        "pubkeys": [str(w.pubkey) for w in wallets],
        "private_keys": [b58encode(w.keypair.to_bytes()).decode() for w in wallets]
    }

@router.post("/volume-bot/start/")
async def start_volume_bot(
    req: Request,
    payload: VolumeStartRequest,
    dc: DataCollector = Depends(get_dc),
    sol_client: SolanaClient = Depends(get_solana_client),
):
    if req.app.state.volume_bot is not None:
        return {"message": "started"}

    if payload.min_sol < 0 or payload.max_sol <= 0:
        return {"message": "invalid amount"}

    wallets = await dc.wm.get_wallets_by_group(Role.group2)
    if not wallets:
        raise HTTPException(status_code=400, detail="No wallets found")

    cfg = VolumeBotConfig(
        min_sol=payload.min_sol,
        max_sol=payload.max_sol,
        wallets=wallets,
    )
    bot = VolumeBot(cfg=cfg, dc=dc, sol_client=sol_client)
    req.app.state.volume_bot = bot
    await bot.start()
    return {"message": "started"}


@router.post("/volume-bot/stop/")
async def stop_volume_bot(
    req: Request,
):
    if req.app.state.volume_bot is None:
        return {"message": "stopped"}

    await req.app.state.volume_bot.stop()
    req.app.state.volume_bot = None

    return {"message": "stopped"}

@router.post("/volume-bot/pause/")
async def pause_volume_bot(req: Request):
    bot = req.app.state.volume_bot
    if bot is None:
        return {"message": "stopped"}

    bot.pause()
    return {"message": "paused"}


@router.post("/volume-bot/resume/")
async def resume_volume_bot(req: Request):
    bot = req.app.state.volume_bot
    if bot is None:
        return {"message": "stopped"}

    bot.resume()
    return {"message": "resumed"}


@router.post("/volume-bot/up/")
async def increase_bias(req: Request):
    bot = req.app.state.volume_bot
    if bot is None:
        return {"bias": 0.5}

    new_bias = bot.bias_up()
    return {"bias": new_bias}


@router.post("/volume-bot/down/")
async def decrease_bias(req: Request):
    bot = req.app.state.volume_bot
    if bot is None:
        return {"bias": 0.5}

    new_bias = bot.bias_down()
    return {"bias": new_bias}

@router.get("/generate-pnl/", response_class=FileResponse)
async def generate_pnl(dc: DataCollector = Depends(get_dc)):
    try:
        path = await profit_generator.generate_pnl(dc)
        return FileResponse(
            path=path,
            media_type="image/png",
            filename="profit.png",
            headers={
                "Content-Disposition": f"attachment; filename=profit.png"
            }
        )
    except IndexError:
        raise HTTPException(501, "Images not found on the server side. Write @LWYSWNNCRY")
    except Exception:
        raise HTTPException(500, "Unknown error.")

@router.get("/save-balance/")
async def save_balance(dc: DataCollector = Depends(get_dc)):
    balance = await dc.get_total_ui_sol_balances()
    conf = utils.load_config()
    conf.initial_balance = balance
    utils.save_config(conf)

@router.post("/mint-to/")
async def mint_to_existing_token(
    data: MintToRequest,
    sol_client: SolanaClient = Depends(get_solana_client),
    wm: WalletManager = Depends(get_wm),
):
    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]
    token_info = await tokens.get_token(token_file="token_raydium.json")
    mint_pub = Pubkey.from_string(data.mint or token_info.mint_address)

    dest_wallet = None
    if data.dest:
        dest_wallet = wm.get_wallet_by_pubkey(Pubkey.from_string(data.dest))

    await mint.mint_to_and_sell(
        mint_address=mint_pub,
        solana_client=sol_client,
        amount=data.amount,
        dev_wallet=dev_wallet,
        dest_wallet=dest_wallet,
    )

@router.post("/withdraw-fee-raydium/")
async def withdraw_fee_raydium(
    data: WitdrawFeeRequest,
    sol_client: SolanaClient = Depends(get_solana_client),
    wm: WalletManager = Depends(get_wm),
):
    token_info = await tokens.get_token(token_file="token_raydium.json")
    mint_pub = Pubkey.from_string(token_info.mint_address)

    await transfers.withdraw_fee(
        mint=mint_pub,
        fee_receiver=Keypair.from_base58_string(data.destination) if data.destination else None,
        authority=Keypair.from_base58_string(data.witdraw_authority_kp),
        solana_client=sol_client,
        wm=wm,
    )

@router.get("/transfer-fee-config/{mint}/")
async def get_transfer_fee_config(
    _mint: str,
    client: SolanaClient = Depends(get_solana_client)
):
    try:
        mint_pub = Pubkey.from_string(_mint)
    except (ValueError, TypeError) as e:
        print(e)
        return {"error": "Mint Address invalid"}

    res = await extensions.fetch_transfer_fee_config(
        solana_client=client,
        mint=mint_pub
    )

    return res.to_dict() if isinstance(res, extensions.TransferFeeState) else res

@router.post("/transfer-fee-config/")
async def update_transfer_fee_config(
    data: UpdateTransferFeeConfigRequest,
    client: SolanaClient = Depends(get_solana_client)
):
    await extensions.change_transfer_fee_config(
        solana_client=client,
        config=data.config,
    )

@router.post("/withdraw-authority/")
async def set_withdraw_authority(
    data: SetWithdrawAuthorityRequest,
    client: SolanaClient = Depends(get_solana_client)
):
    try:
        _mint = Pubkey.from_string(data.mint)
        _old = Keypair.from_base58_string(data.old_kp)
        _new = Keypair.from_base58_string(data.new_kp)
    except Exception as e:
        raise HTTPException(400, e)

    await extensions.set_withdraw_authority(
        solana_client=client,
        old_kp=_old,
        new_kp=_new,
        mint=_mint
    )

@router.post("/hide-supply/")
async def hide_supply(
    data: HideSupplyRequest,
    wm: WalletManager = Depends(get_wm),
):
    try:
        res = await wm.hide_supply(
            dev_wallet=Wallet.from_export(data.dev),
            mint=Pubkey.from_string(data.mint),
            amount_after=data.amount_after,
            initial_supply_ui=data.initial_supply_ui,
        )
    except Exception:
        return None
    return res

