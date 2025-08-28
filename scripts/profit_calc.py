import asyncio
from typing import Final
import httpx
import xml.etree.ElementTree as ET

MOSCOW_AVG_SALARY_RUB: Final[float] = 85700.0

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

async def main():
    try:
        initial_balance = float(input("Enter initial balance in SOL: ").strip())
        current_balance_sol = float(input("Enter current balance in SOL: ").strip())
    except ValueError:
        print("❌ Invalid number")
        return

    print("📡 Fetching prices...")
    sol_price_usd, usd_to_rub = await asyncio.gather(
        fetch_sol_price_usd(),
        fetch_usd_to_rub(),
    )

    pnl_sol = current_balance_sol - initial_balance
    pnl_usd = pnl_sol * sol_price_usd
    pnl_rub = pnl_usd * usd_to_rub

    pct_change = ((current_balance_sol - initial_balance) / initial_balance) * 100
    salary_ratio = pnl_rub / MOSCOW_AVG_SALARY_RUB

    sign = "+" if pnl_sol >= 0 else "-"
    print("\n=== 📈 PROFIT REPORT ===")
    print(f"🔹 PnL SOL: {sign}{abs(pnl_sol):.1f}")
    print(f"💵 PnL USD: {sign}${abs(pnl_usd):,.2f}")
    print(f"💰 PnL RUB: {sign}{abs(pnl_rub):,.2f} ₽")
    print(f"📊 PnL %: {sign}{abs(pct_change):.2f}%")
    print(f"🧅 Средних (медианных) Московских зарплат: {salary_ratio:.1f} (от 85 700 ₽)")

    print("\n📊 Курсы:")
    print(f"1 SOL = ${sol_price_usd:.2f}")
    print(f"1 USD = {usd_to_rub:.2f} ₽")


if __name__ == "__main__":
    asyncio.run(main())
