from . import start, settings, contracts, control, status

routers = (
    start.router,
    settings.router,
    contracts.router,
    control.router,
    status.router,
)

__all__ = ["routers"]
