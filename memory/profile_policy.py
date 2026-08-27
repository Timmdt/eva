from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileAccess:
    identity: str | None
    profile: str
    allow_private_memory: bool
    context_note: str


def access_for_identity(identity: str | None) -> ProfileAccess:
    clean = (identity or "").strip()
    if not clean or clean.lower() == "unknown":
        return ProfileAccess(None, "unknown", False,
                             "Unbekannter Nutzer: keinen privaten Memory-Kontext laden.")
    if clean.lower() == "visitor":
        return ProfileAccess("Visitor", "visitor", False,
                             "Besucherprofil: nur allgemeinen Kontext verwenden.")
    return ProfileAccess(clean, "personal", True,
                         f"Registriertes lokales Profil: {clean}.")
