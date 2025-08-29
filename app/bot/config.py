from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import yaml
import os

CONFIG_PATH = os.getenv("BOT_CONFIG_PATH", "bot/config.yaml")

@dataclass
class RunSchedule:
    enabled: bool = False                  # автоциклы включены?
    interval_sec: int = 600                # пауза между циклами, сек
    active_from: str = "00:00"             # рабочее окно (локальное время)
    active_to: str = "23:59"

@dataclass
class BabloRuntimeConfig:
    # Прямое отображение на BabloConfig:
    token_amount_ui: List[int] = field(default_factory=lambda: [10])     # миллионов токенов UI
    wsol_amount_ui: List[float] = field(default_factory=lambda: [0.20])  # SOL в ликвидность
    profit_threshold_sol: float = 0.05
    cycle_timeout_sec: int = 120
    mode: str = "manual"                       # manual | auto (auto не реализован в Bablo)

    # Доп. опции бота
    delays_ms: int = 0                         # общие задержки/джиттер (на будущее)
    last_ca: Optional[str] = None              # для manual режима
    schedule: RunSchedule = field(default_factory=RunSchedule)

@dataclass
class AppConfig:
    bablo: BabloRuntimeConfig = field(default_factory=BabloRuntimeConfig)

def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        cfg = AppConfig()
        save_config(cfg)
        return cfg
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    # простая ручная десериализация
    sched = raw.get("bablo", {}).get("schedule", {}) if raw else {}
    schedule = RunSchedule(**sched) if sched else RunSchedule()
    bablo = raw.get("bablo", {}) if raw else {}
    cfg = AppConfig(
        bablo=BabloRuntimeConfig(
            token_amount_ui=bablo.get("token_amount_ui", [10]),
            wsol_amount_ui=bablo.get("wsol_amount_ui", [0.20]),
            profit_threshold_sol=bablo.get("profit_threshold_sol", 0.05),
            cycle_timeout_sec=bablo.get("cycle_timeout_sec", 120),
            mode=bablo.get("mode", "manual"),
            delays_ms=bablo.get("delays_ms", 0),
            last_ca=bablo.get("last_ca"),
            schedule=schedule,
        )
    )
    return cfg

def save_config(cfg: AppConfig) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump({"bablo": asdict(cfg.bablo)}, f, sort_keys=False, allow_unicode=True)
