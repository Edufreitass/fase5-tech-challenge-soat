import re

from shared.time import agora_iso


def test_formato_utc_com_z() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", agora_iso())
