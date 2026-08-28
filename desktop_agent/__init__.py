"""Optional desktop webcam client. It never controls Wake-on-LAN or shutdown."""

from .eva_client import EVAClient

__all__ = ["EVAClient"]
