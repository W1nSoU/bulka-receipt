from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

# Максимум N чеків за вікно часу (секунди) на одного юзера
_LIMIT = 20
_WINDOW = 86400  # 24 години

_timestamps: Dict[int, List[float]] = defaultdict(list)


def check_rate_limit(telegram_id: int) -> bool:
    """
    Перевіряє чи юзер не перевищив ліміт.

    Returns:
        True — дозволено, False — заблоковано.
    """
    now = time.monotonic()
    ts = _timestamps[telegram_id]
    ts[:] = [t for t in ts if now - t < _WINDOW]
    if len(ts) >= _LIMIT:
        return False
    ts.append(now)
    return True


def remaining(telegram_id: int) -> int:
    """Кількість чеків, що залишилась у поточному вікні."""
    now = time.monotonic()
    ts = _timestamps[telegram_id]
    active = [t for t in ts if now - t < _WINDOW]
    return max(0, _LIMIT - len(active))
