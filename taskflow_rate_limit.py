from collections import OrderedDict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window: int) -> None:
        self.max_requests = max_requests
        self.window = window
        self.history: OrderedDict[str, deque[float]] = OrderedDict()

    def allow(self, client: str, now: float) -> bool:
        cutoff = now - self.window
        while self.history:
            oldest = next(iter(self.history))
            if self.history[oldest][-1] > cutoff:
                break
            self.history.popitem(last=False)
        history = self.history.setdefault(client, deque())
        while history and history[0] <= cutoff:
            history.popleft()
        if len(history) >= self.max_requests:
            return False
        history.append(now)
        self.history.move_to_end(client)
        return True
