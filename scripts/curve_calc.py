#!/usr/bin/env python3
"""
Pump.fun ▸ расчёт ΔSOL для перехода
от market-cap A → к market-cap B  (в USD).

▪ Если указать только <target>, считается рост от дефолтного Vs (30 SOL).
▪ Можно задать начальный MC через --start или --vs.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
import httpx

# ---------- постоянные платформы  ------------------------------------------
INITIAL_VS_SOL   = 30.0000852                # виртуальный SOL-резерв по умолчанию
INITIAL_VT_TOKEN = 1_073_000_191.0      # виртуальный токен-резерв
TOTAL_SUPPLY     = 1_000_000_000.0      # фиксированный supply
K_CONST = INITIAL_VS_SOL * INITIAL_VT_TOKEN
# ----------------------------------------------------------------------------


@dataclass(slots=True)
class Result:
    extra_sol: float
    extra_usd: float
    start_mc_usd: float
    target_mc_usd: float
    new_price_sol: float
    new_price_usd: float


# ─────────────────────────────────────────────────────────────────────────────
def _vs_from_mc(mc_sol: float) -> float:
    """Vs, соответствующий market-cap в SOL."""
    return math.sqrt(mc_sol * K_CONST / TOTAL_SUPPLY)


def _delta_sol(vs_start: float, mc_target_sol: float) -> float:
    """Сколько SOL долить, чтобы дойти до mc_target_sol (SOL)."""
    vs_target = _vs_from_mc(mc_target_sol)
    if vs_target <= vs_start:
        raise ValueError("Target MC не выше стартового.")
    return vs_target - vs_start


def calc_delta(
    mc_target_usd: float,
    sol_price_usd: float,
    *,
    start_mc_usd: float | None = None,
    vs_start_sol: float | None = None,
) -> Result:
    """
    Главная вычислительная обёртка.

    start_mc_usd и vs_start_sol взаимоисключающие:
      • если дан start_mc_usd → Vs выводим из него;
      • иначе берём vs_start_sol (или дефолт 30 SOL).
    """
    if start_mc_usd is not None and vs_start_sol is not None:
        raise ValueError("Укажите либо --start, либо --vs, но не оба сразу.")

    # стартовый Vs
    if start_mc_usd is not None:
        mc_start_sol = start_mc_usd / sol_price_usd
        vs_start = _vs_from_mc(mc_start_sol)
    else:
        vs_start = vs_start_sol if vs_start_sol is not None else INITIAL_VS_SOL
        mc_start_sol = vs_start**2 / K_CONST * TOTAL_SUPPLY
        start_mc_usd = mc_start_sol * sol_price_usd

    # целевой MC → SOL
    mc_target_sol = mc_target_usd / sol_price_usd

    delta_sol = _delta_sol(vs_start, mc_target_sol)
    price_sol = (_vs_from_mc(mc_target_sol))**2 / K_CONST
    price_usd = price_sol * sol_price_usd

    return Result(
        extra_sol=delta_sol,
        extra_usd=delta_sol * sol_price_usd,
        start_mc_usd=start_mc_usd,
        target_mc_usd=mc_target_usd,
        new_price_sol=price_sol,
        new_price_usd=price_usd,
    )

def get_sol_price_usd() -> float:
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "solana", "vs_currencies": "usd"}
    with httpx.Client() as client:
        r = client.get(url=url, params=params)
        r.raise_for_status()
        return r.json()["solana"]["usd"]


# ───────────────────────────── CLI ───────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Pump.fun bonding-curve: ΔSOL от MC-start → MC-target"
    )
    p.add_argument(
        "target",
        type=float,
        help="Целевой market-cap (USD)",
    )
    p.add_argument(
        "--start",
        type=float,
        dest="start_mc",
        help="Стартовый MC (USD). Если не задан, берётся Vs=--vs",
    )
    p.add_argument(
        "--vs",
        type=float,
        dest="vs_sol",
        help=f"Стартовый виртуальный Vs (SOL). По умолчанию {INITIAL_VS_SOL}",
    )
    args = p.parse_args()

    sol_price = get_sol_price_usd()

    res = calc_delta(
        mc_target_usd=args.target,
        sol_price_usd=sol_price,
        start_mc_usd=args.start_mc,
        vs_start_sol=args.vs_sol,
    )

    print("\n── Результат ─────────────────────────────────────────────")
    print(f"Стартовый MC              : {res.start_mc_usd:,.2f} USD")
    print(f"Целевой  MC               : {res.target_mc_usd:,.2f} USD")
    print(f"Курс SOL                  : {sol_price:.2f} USD")
    print(f"Нужно долить              : {res.extra_sol:.4f} SOL "
          f"(≈ {res.extra_usd:,.2f} USD)")
    print(f"Новая цена токена         : {res.new_price_sol:.10f} SOL "
          f"(≈ {res.new_price_usd:.10f} USD)")
