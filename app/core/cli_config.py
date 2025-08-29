from __future__ import annotations

import asyncio
from typing import Callable, Optional

from .bablo_bot import BabloConfig

async def ainput(prompt: str = "") -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))

def _parse_list_of_ints(s: str) -> list[int]:
    if s.strip() == "":
        raise ValueError("empty")
    parts = [p.strip() for p in s.replace(";", ",").split(",")]
    out: list[int] = []
    for p in parts:
        if p == "":
            continue
        out.append(int(p))
    if not out:
        raise ValueError("no values")
    return out

def _parse_list_of_floats(s: str) -> list[float]:
    if s.strip() == "":
        raise ValueError("empty")
    parts = [p.strip() for p in s.replace(";", ",").split(",")]
    out: list[float] = []
    for p in parts:
        if p == "":
            continue
        out.append(float(p))
    if not out:
        raise ValueError("no values")
    return out

def _parse_int(s: str) -> int:
    return int(s.strip())

def _parse_float(s: str) -> float:
    return float(s.strip())

async def _ask(
    title: str,
    example: str,
    *,
    default_str: str,
    parser: Callable[[str], object],
    validator: Optional[Callable[[object], None]] = None,
) -> object:
    """
    Универсальный промпт: показывает заголовок, пример, дефолт (в []),
    парсит ввод и валидирует; пустой ввод -> дефолт.
    """
    while True:
        raw = await ainput(f"Предварительная настройка\n{title}\n{example}\n[{default_str}] >>> ")
        raw = raw.strip()
        try:
            val = parser(raw) if raw != "" else parser(default_str)
            if validator:
                validator(val)
            return val
        except Exception as e:
            print(f"✖ Некорректное значение: {e}. Попробуй ещё раз.")

def _validate_mode(v: str):
    vv = v.lower()
    if vv not in ("manual", "auto"):
        raise ValueError("допустимо 'manual' или 'auto'")

def _validate_positive_or_zero_float(v: float):
    if v < 0:
        raise ValueError("должно быть ≥ 0")

def _validate_positive_or_zero_int(v: int):
    if v < 0:
        raise ValueError("должно быть ≥ 0")

def _validate_list_nonempty_int(v: list[int]):
    if not v:
        raise ValueError("нужен хотя бы один элемент")

def _validate_list_nonempty_float(v: list[float]):
    if not v:
        raise ValueError("нужен хотя бы один элемент")

async def get_cfg_from_user_cli(default: Optional[BabloConfig] = None) -> BabloConfig:
    """
    Ассистент получения конфигурации для Bablo через CLI.
    Поддерживает:
      - списки через запятую/точку с запятой: "1000, 900"
      - одиночные значения
      - нули (0)
      - строки 'manual'/'auto' для режима
      - пустой ввод = оставить дефолт
    """
    d = default or BabloConfig()

    # 1) token_amount_ui: список int
    token_amount_ui = await _ask(
        title="1)Количество токенов в миллионах",
        example="пример: 1000, 900  (можно один: 1000)",
        default_str=",".join(str(x) for x in d.token_amount_ui),
        parser=_parse_list_of_ints,
        validator=_validate_list_nonempty_int,
    )

    # 2) wsol_amount_ui: список float
    wsol_amount_ui = await _ask(
        title="2)Количество Солан",
        example="пример: 3, 2.5, 0   (ноль допустим)",
        default_str=",".join(str(x) for x in d.wsol_amount_ui),
        parser=_parse_list_of_floats,
        validator=_validate_list_nonempty_float,
    )

    # 3) порог профита, float ≥ 0
    profit_threshold_sol = await _ask(
        title="3) Порог профита (SOL)",
        example="пример: 0.05  (0 — сразу по таймеру/ручному сигналу)",
        default_str=str(d.profit_threshold_sol),
        parser=_parse_float,
        validator=_validate_positive_or_zero_float,
    )

    # 4) timeout цикла (сек), int ≥ 0
    cycle_timeout_sec = await _ask(
        title="4) Таймер цикла (сек)",
        example="пример: 120  (0 — таймер отключён, только PnL-триггер)",
        default_str=str(d.cycle_timeout_sec),
        parser=_parse_int,
        validator=_validate_positive_or_zero_int,
    )

    # 5) режим работы
    mode = await _ask(
        title="5) Режим работы",
        example="пример: manual  или  auto",
        default_str=d.mode,
        parser=lambda s: (s.strip() or d.mode).lower(),
        validator=_validate_mode,
    )

    # 6) пауза для auto (сек), int ≥ 0
    auto_sleep_sec = await _ask(
        title="6) Пауза между авто-циклами (сек) [используется только при mode=auto]",
        example="пример: 300  (0 — без паузы)",
        default_str=str(d.auto_sleep_sec),
        parser=_parse_int,
        validator=_validate_positive_or_zero_int,
    )

    cfg = BabloConfig(
        token_amount_ui=token_amount_ui,           # type: ignore[arg-type]
        wsol_amount_ui=wsol_amount_ui,             # type: ignore[arg-type]
        profit_threshold_sol=float(profit_threshold_sol),  # type: ignore[arg-type]
        cycle_timeout_sec=int(cycle_timeout_sec),          # type: ignore[arg-type]
        mode=str(mode),                                     # type: ignore[arg-type]
        auto_sleep_sec=int(auto_sleep_sec),                 # type: ignore[arg-type]
    )

    print(
        "\nИтоговая конфигурация:\n"
        f"  token_amount_ui   = {cfg.token_amount_ui}\n"
        f"  wsol_amount_ui    = {cfg.wsol_amount_ui}\n"
        f"  profit_threshold  = {cfg.profit_threshold_sol}\n"
        f"  cycle_timeout_sec = {cfg.cycle_timeout_sec}\n"
        f"  mode              = {cfg.mode}\n"
        f"  auto_sleep_sec    = {cfg.auto_sleep_sec}\n"
    )
    return cfg
