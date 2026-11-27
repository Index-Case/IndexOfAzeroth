# The Index of Azeroth. Copyright 2026 Index Case <indexofazeroth@pm.me>. PolyForm Strict 1.0.0, see LICENSE.md.
import collections

WINDOW = 60.0
GAP = 2.0
SEQ = 256
SLOW = 0.1


class LinkStats:
    def __init__(self):
        self.frames = collections.deque()
        self.lost = collections.deque()
        self.slow = collections.deque()
        self.stale = collections.deque()
        self.last = None
        self.unread_why = None
        self.unread_seen = set()

    def behind(self, seq, now):
        if self.last is None:
            return False
        prev, at = self.last
        old = (seq - prev) % SEQ >= SEQ // 2 and now - at <= GAP
        if old:
            self.stale.append((now, 1))
        return old

    def frame(self, seq, kind, now):
        if self.last is not None:
            prev, at = self.last
            skipped = (seq - prev) % SEQ - 1
            if 0 < skipped < SEQ // 2 and now - at <= GAP:
                self.lost.append((now, skipped))
        self.last = (seq, now)
        self.frames.append((now, kind))
        self.trim(now)

    def unread(self, seq, why, now):
        new = why not in self.unread_seen
        self.unread_seen.add(why)
        self.unread_why = why
        self.frame(seq, "unread", now)
        return new

    def most(self, kind, now):
        self.trim(now)
        ts = [t for t, k in self.frames if k == kind]
        return max((b - a for a, b in zip(ts, ts[1:])), default=None)

    def work(self, seconds, now):
        if seconds > SLOW:
            self.slow.append((now, seconds))

    def trim(self, now):
        for q in (self.frames, self.lost, self.slow, self.stale):
            while q and now - q[0][0] > WINDOW:
                q.popleft()

    def summary(self, now):
        self.trim(now)
        span = max(1e-6, min(WINDOW, now - self.frames[0][0])) if len(self.frames) > 1 else None
        read, lost = len(self.frames), sum(n for _, n in self.lost)
        times = collections.defaultdict(list)
        for t, k in self.frames:
            times[k].append(t)
        kinds = {}
        for k, ts in times.items():
            gaps = [b - a for a, b in zip(ts, ts[1:])]
            kinds[k] = {"n": len(ts), "every": round(sum(gaps) / len(gaps), 2) if gaps else None,
                        "most": round(max(gaps), 2) if gaps else None, "age": round(now - ts[-1], 1)}
        return {"fps": round(read / span, 1) if span else 0, "lost": lost, "stale": len(self.stale),
                "lostPct": round(100 * lost / (read + lost), 1) if read + lost else 0,
                "stalls": len(self.slow), "stallMost": round(1000 * max((s for _, s in self.slow), default=0)),
                "kinds": kinds, "unreadWhy": self.unread_why if "unread" in kinds else None}
