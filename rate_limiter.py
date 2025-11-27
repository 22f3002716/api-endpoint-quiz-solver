"""
Rate Limiter for Gemini API Free Tier
Tracks and enforces: RPM (15), TPM (1M), RPD (1500)
Prevents hitting free tier limits during quiz solving
"""

import time
import asyncio
from typing import Dict, Tuple
from datetime import datetime, timedelta
from collections import deque
from logger import quiz_logger


class GeminiRateLimiter:
    """
    Thread-safe rate limiter for Gemini 2.5 Flash Free Tier.
    Tracks requests and tokens per minute/day, auto-waits before limits.
    """
    
    def __init__(
        self,
        rpm_limit: int = 10,       # Requests per minute (Gemini 2.5 Flash FREE tier actual limit)
        tpm_limit: int = 1_000_000, # Tokens per minute
        rpd_limit: int = 1500      # Requests per day (hybrid: Flash-Lite=1000 + Flash=250)
    ):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.rpd_limit = rpd_limit  # Effective limit with hybrid Flash/Flash-Lite strategy
        
        # Deques to track requests with timestamps
        self.requests_minute = deque()  # (timestamp, tokens_used)
        self.requests_day = deque()     # (timestamp, tokens_used)
        
        # Current period tracking
        self.current_minute_start = time.time()
        self.current_day_start = datetime.now().date()
        
        quiz_logger.info(
            f"🚦 Rate limiter initialized: RPM={rpm_limit} (FREE tier), TPM={tpm_limit:,}, RPD={rpd_limit}"
        )
    
    def _clean_old_requests(self):
        """Remove requests older than tracking window."""
        now = time.time()
        current_date = datetime.now().date()
        
        # Clean minute window (keep last 60 seconds)
        while self.requests_minute and now - self.requests_minute[0][0] > 60:
            self.requests_minute.popleft()
        
        # Clean day window (keep only today)
        while self.requests_day:
            req_date = datetime.fromtimestamp(self.requests_day[0][0]).date()
            if req_date < current_date:
                self.requests_day.popleft()
            else:
                break
    
    def get_current_usage(self) -> Dict[str, Tuple[int, int]]:
        """
        Returns current usage stats.
        Returns: {
            'rpm': (current, limit),
            'tpm': (current, limit),
            'rpd': (current, limit)
        }
        """
        self._clean_old_requests()
        
        # Count requests in last minute
        rpm_current = len(self.requests_minute)
        
        # Sum tokens in last minute
        tpm_current = sum(tokens for _, tokens in self.requests_minute)
        
        # Count requests today
        rpd_current = len(self.requests_day)
        
        return {
            'rpm': (rpm_current, self.rpm_limit),
            'tpm': (tpm_current, self.tpm_limit),
            'rpd': (rpd_current, self.rpd_limit)
        }
    
    def _calculate_wait_time(self, estimated_tokens: int = 5000) -> float:
        """
        Calculate how long to wait before making next request.
        Returns: seconds to wait (0 if safe to proceed)
        """
        self._clean_old_requests()
        
        usage = self.get_current_usage()
        rpm_current, _ = usage['rpm']
        tpm_current, _ = usage['tpm']
        rpd_current, _ = usage['rpd']
        
        # Check if we're at risk of hitting limits
        wait_times = []
        
        # RPM check (leave 1 request buffer for FREE tier)
        if rpm_current >= self.rpm_limit - 1:
            oldest_request = self.requests_minute[0][0]
            wait_until_oldest_expires = 60 - (time.time() - oldest_request)
            wait_times.append(max(0, wait_until_oldest_expires))
            quiz_logger.warning(
                f"⚠️  Near RPM limit: {rpm_current}/{self.rpm_limit} requests"
            )
        
        # TPM check (leave 50K token buffer)
        if tpm_current + estimated_tokens >= self.tpm_limit - 50_000:
            # Wait for oldest high-token request to expire
            if self.requests_minute:
                oldest_request = self.requests_minute[0][0]
                wait_until_oldest_expires = 60 - (time.time() - oldest_request)
                wait_times.append(max(0, wait_until_oldest_expires))
                quiz_logger.warning(
                    f"⚠️  Near TPM limit: {tpm_current:,}/{self.tpm_limit:,} tokens"
                )
        
        # RPD check (hard stop if at limit)
        if rpd_current >= self.rpd_limit:
            quiz_logger.error(
                f"🛑 RPD limit reached: {rpd_current}/{self.rpd_limit} requests today"
            )
            # Wait until midnight
            now = datetime.now()
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            seconds_until_midnight = (midnight - now).total_seconds()
            return seconds_until_midnight
        
        return max(wait_times) if wait_times else 0
    
    async def wait_if_needed(self, estimated_tokens: int = 5000):
        """
        Check rate limits and wait if necessary before making API call.
        Call this BEFORE each LLM request.
        """
        wait_time = self._calculate_wait_time(estimated_tokens)
        
        if wait_time > 0:
            quiz_logger.warning(
                f"⏳ Rate limit protection: waiting {wait_time:.1f}s before next request"
            )
            await asyncio.sleep(wait_time)
    
    def record_request(self, tokens_used: int):
        """
        Record a completed API request.
        Call this AFTER each successful LLM response.
        """
        now = time.time()
        
        self.requests_minute.append((now, tokens_used))
        self.requests_day.append((now, tokens_used))
        
        self._clean_old_requests()
        
        # Log current usage
        usage = self.get_current_usage()
        rpm_current, _ = usage['rpm']
        tpm_current, _ = usage['tpm']
        rpd_current, _ = usage['rpd']
        
        quiz_logger.debug(
            f"📊 Rate usage: RPM={rpm_current}/{self.rpm_limit}, "
            f"TPM={tpm_current:,}/{self.tpm_limit:,}, "
            f"RPD={rpd_current}/{self.rpd_limit}"
        )
    
    def get_usage_summary(self) -> str:
        """Get formatted usage summary for logging."""
        usage = self.get_current_usage()
        
        rpm_current, rpm_limit = usage['rpm']
        tpm_current, tpm_limit = usage['tpm']
        rpd_current, rpd_limit = usage['rpd']
        
        rpm_pct = (rpm_current / rpm_limit * 100) if rpm_limit > 0 else 0
        tpm_pct = (tpm_current / tpm_limit * 100) if tpm_limit > 0 else 0
        rpd_pct = (rpd_current / rpd_limit * 100) if rpd_limit > 0 else 0
        
        return (
            f"Rate Limiter Status:\n"
            f"  RPM: {rpm_current}/{rpm_limit} ({rpm_pct:.1f}%)\n"
            f"  TPM: {tpm_current:,}/{tpm_limit:,} ({tpm_pct:.1f}%)\n"
            f"  RPD: {rpd_current}/{rpd_limit} ({rpd_pct:.1f}%)"
        )


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> GeminiRateLimiter:
    """Get or create global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter
