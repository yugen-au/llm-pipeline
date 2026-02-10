"""
Rate limiting utilities for external API calls.
"""
import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Simple rate limiter to ensure we don't exceed API quotas.

    Uses a sliding window approach to track request timestamps.
    """

    def __init__(self, max_requests: int, time_window_seconds: float):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in the time window
            time_window_seconds: Time window in seconds (e.g., 60 for per-minute)
        """
        self.max_requests = max_requests
        self.time_window_seconds = time_window_seconds
        self.request_times: list[float] = []

    def wait_if_needed(self) -> None:
        """Wait if necessary to comply with rate limit."""
        now = time.time()
        cutoff_time = now - self.time_window_seconds
        self.request_times = [t for t in self.request_times if t > cutoff_time]

        if len(self.request_times) >= self.max_requests:
            oldest_request = self.request_times[0]
            wait_until = oldest_request + self.time_window_seconds
            wait_time = wait_until - now

            if wait_time > 0:
                logger.info(f"  Rate limit reached. Waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                now = time.time()
                cutoff_time = now - self.time_window_seconds
                self.request_times = [
                    t for t in self.request_times if t > cutoff_time
                ]

        self.request_times.append(now)

    def get_wait_time(self) -> float:
        """Get seconds to wait before next request (0 if can request immediately)."""
        now = time.time()
        cutoff_time = now - self.time_window_seconds
        active_requests = [t for t in self.request_times if t > cutoff_time]
        if len(active_requests) < self.max_requests:
            return 0
        oldest_request = active_requests[0]
        wait_until = oldest_request + self.time_window_seconds
        return max(0, wait_until - now)

    def reset(self) -> None:
        """Clear all recorded request times."""
        self.request_times = []


__all__ = ["RateLimiter"]
