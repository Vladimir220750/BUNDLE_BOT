import asyncio
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import xml.etree.ElementTree as ET
import httpx
import random
from uuid import uuid4

from io import BytesIO

from ..core.data_collector import DataCollector
from ..core.logger import logger
from .utils import load_config

MOSCOW_AVG_SALARY_RUB: float = 85700.0
TMP_DIR = Path("/data/tmp/pnl_images")
FONT_PATH_SEMI_BOLD = "/data/tmp/Montserrat-SemiBold.ttf"
FONT_PATH_THIN_ITALIC = "/data/tmp/Montserrat-ThinItalic.ttf"

async def fetch_sol_price_usd() -> float:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "solana", "vs_currencies": "usd"}
    async with httpx.AsyncClient() as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()["solana"]["usd"]

async def fetch_usd_to_rub() -> float:
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode").text
            if char_code == "USD":
                value = valute.find("Value").text.replace(",", ".")
                nominal = int(valute.find("Nominal").text)
                return float(value) / nominal
        raise ValueError("USD not found in CBR response")

async def generate_pnl(dc: DataCollector) -> Path:
    try:
        config = load_config()

        sol_price_usd, usd_to_rub, current_balance = await asyncio.gather(
            fetch_sol_price_usd(),
            fetch_usd_to_rub(),
            dc.get_total_ui_sol_balances(),
        )
        pnl_sol = current_balance - config.initial_balance
        pnl_usd = pnl_sol * sol_price_usd
        pnl_rub = pnl_usd * usd_to_rub
        pct_change = (pnl_sol / config.initial_balance) * 100 if config.initial_balance > 0 else 0.0
        salary_ratio = pnl_rub / MOSCOW_AVG_SALARY_RUB

        try:
            url = random.choice(config.image_links)
            async with httpx.AsyncClient() as client:
                r = await client.get(url)
                r.raise_for_status()
        except IndexError:
            logger.error("Empty List of Images")
            raise
        except Exception as e:
            logger.exception(e)
            raise

        base_img = Image.open(BytesIO(r.content)).convert("RGBA")
        width, height = base_img.size
        side = min(width, height)
        base_img = base_img.crop((
            (width - side) // 2,
            (height - side) // 2,
            (width + side) // 2,
            (height + side) // 2,
        ))
        base_img = base_img.resize((1024, 1024), Image.LANCZOS)
        width, height = base_img.size

        txt_layer = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_layer)

        font_pct = ImageFont.truetype(FONT_PATH_SEMI_BOLD, size=200)
        font_sol = ImageFont.truetype(FONT_PATH_SEMI_BOLD, size=170)
        font_small = ImageFont.truetype(FONT_PATH_SEMI_BOLD, size=44)

        center_x = width // 2

        if pct_change > 0:
            color = "lime"
            symbol = "+"
        elif pct_change < 0:
            color = "red"
            symbol = "-"
        else:
            color = "white"
            symbol = ""

        def draw_text_with_bg(text: str, x: int, y: int, font, fill: str, anchor="mm", padding=16):
            bbox = draw.textbbox((0, 0), text, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if anchor == "mm":
                box = (x - w // 2 - padding, y - h // 2 - padding, x + w // 2 + padding, y + h // 2 + padding)
            elif anchor == "ma":
                box = (x - w // 2 - padding, y - padding, x + w // 2 + padding, y + h + padding)
            else:
                raise ValueError("Unsupported anchor")
            draw.rectangle(box, fill=(0, 0, 0, 100))
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        draw.text((center_x, 250), f"{symbol}{pct_change:.1f}%", font=font_pct, fill=color, anchor="mm")
        draw.text((center_x, 512), f"{symbol}{pnl_sol:.1f} SOL", font=font_sol, fill=color, anchor="mm")
        draw_text_with_bg(f"{symbol}{pnl_usd:,.1f}$", center_x - 380, 880, font_small, color)
        draw_text_with_bg(f"{symbol}{pnl_rub:,.0f}₽", center_x + 380, 880, font_small, color)
        draw_text_with_bg(f"{symbol}{salary_ratio:.1f} московских зарплат", center_x, 960, font_small, color)

        base_img = Image.alpha_composite(base_img, txt_layer)

        TMP_DIR.mkdir(parents=True, exist_ok=True)
        file_id = uuid4().hex
        file_path = TMP_DIR / f"pnl_{file_id}.png"

        with open(file_path, "wb") as f:
            base_img.save(f, format="PNG")

        return file_path
    except Exception as e:
        logger.exception(e)
        raise
