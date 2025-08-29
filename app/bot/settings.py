from app.core.config import Settings, settings as core_settings


def load_settings() -> Settings:
    return core_settings


SETTINGS = load_settings()
