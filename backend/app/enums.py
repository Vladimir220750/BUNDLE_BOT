from enum import Enum

class Role(str, Enum):
    dev = "dev"
    fund = "fund"
    group1 = "group1"
    group2 = "group2"
    archive = "archive"

class TokenType(str, Enum):
    raydium = "raydium"
    pumpfun = "pumpfun"

