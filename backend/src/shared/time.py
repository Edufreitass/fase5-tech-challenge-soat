from datetime import UTC, datetime, timedelta


def agora_iso() -> str:
    """ISO-8601 UTC com milissegundos e sufixo `Z` (ex.:
    2026-10-18T15:10:00.000Z)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def somar_segundos(iso: str, segundos: int) -> str:
    base = datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(seconds=segundos)
    return base.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
