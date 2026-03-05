"""
EV Mitra — core/circuit_breaker.py
Generic circuit breaker with automatic cooldown.
"""

import threading
import time

from core.config import CIRCUIT_BREAKER_THRESHOLD, CIRCUIT_BREAKER_COOLDOWN_SEC, logger


class CircuitBreaker:
    """
    Opens after `threshold` consecutive failures.
    Auto-closes after `cooldown_sec` seconds so recovery is possible.
    """

    def __init__(self, name: str = "default",
                 threshold: int = CIRCUIT_BREAKER_THRESHOLD,
                 cooldown_sec: int = CIRCUIT_BREAKER_COOLDOWN_SEC):
        self.name = name
        self.threshold = threshold
        self.cooldown_sec = cooldown_sec
        self._failures = 0
        self._opened_at: float | None = None
        self._reason = ""
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return False
            if time.time() - self._opened_at >= self.cooldown_sec:
                # Cooldown elapsed — half-open: allow next call to probe
                logger.info("CircuitBreaker[%s] cooldown elapsed, moving to half-open", self.name)
                self._opened_at = None
                self._failures = 0
                self._reason = ""
                return False
            return True

    @property
    def reason(self) -> str:
        return self._reason

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._reason = ""

    def record_failure(self, reason: str = ""):
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.time()
                self._reason = reason
                logger.warning("CircuitBreaker[%s] OPENED after %d failures: %s",
                               self.name, self._failures, reason)

    def trip(self, reason: str):
        """Immediately open the circuit (e.g. unrecoverable 401/403)."""
        with self._lock:
            self._opened_at = time.time()
            self._reason = reason
            self._failures = self.threshold
            logger.warning("CircuitBreaker[%s] TRIPPED: %s", self.name, reason)

    @property
    def status(self) -> str:
        if self.is_open:
            return "open"
        with self._lock:
            if self._failures > 0:
                return "half-open"
        return "closed"
