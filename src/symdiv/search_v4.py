"""Additional deterministic controls and event-driven retained-frontier search.

These policies reuse v3's source interpreter and acceptance boundary verbatim.
Coverage and sink distance are local policies, not implementations of KLEE.
"""
import heapq
from collections import Counter

from .extract import _children, _walk
from .search import Search


class SearchV4(Search):
    EXTRA_POLICIES = ("bfs", "reverse", "coverage", "distance", "discrepancy")

    def __init__(self, prepared, policy="dfs", **kwargs):
        self.requested_policy = policy
        self.edge_visits = Counter()
        self.node_costs = {}
        super().__init__(prepared, policy="dfs" if policy in self.EXTRA_POLICIES else policy, **kwargs)
        self.set_policy(policy)

    def priority(self, state, sequence):
        if self.policy == "bfs":
            return (len(state.trace), sequence)
        if self.policy in ("reverse", "discrepancy"):
            return (sum(t["take"] if self.policy == "reverse" else not t["take"]
                        for t in state.trace), -sequence)
        if self.policy == "coverage":
            counts = [self.edge_visits[(t["branch_id"], t["visit"], t["take"])]
                      for t in state.trace]
            return (counts[-1] if counts else 0, sum(counts), -sequence)
        return super().priority(state, sequence)

    def distance(self, frames):
        """Optimistic number of source statements until a sink, with loop bodies.

        No feasibility or neural information is used. Ties use DFS. A loop is
        counted once; the exact interpreter still enforces every iteration.
        """
        def cost(node):
            identity = node.get("id", "")
            if identity in self.node_costs:
                return self.node_costs[identity]
            children = list(_children(node))
            kind = node.get("kind")
            if kind == "CompoundStmt":
                value = frame_cost([("node", c) for c in children])
            elif kind == "IfStmt":
                options = [cost(c) for c in children[1:]] + ([(1, False)] if len(children) < 3 else [])
                reachable = [(n + 1, found) for n, found in options if found]
                value = min(reachable) if reachable else (1 + min(n for n, _ in options), False)
            elif kind in ("ForStmt", "WhileStmt", "DoStmt"):
                body = children[-1] if kind != "DoStmt" else children[0]
                n, found = cost(body)
                value = (1 + n, found)
            else:
                value = (1, any(n.get("opcode") in ("/", "%", "/=", "%=") for n in _walk(node)))
            self.node_costs[identity] = value
            return value

        def frame_cost(pending):
            total = 0
            for frame in pending:
                if frame[0] == "scope":
                    continue
                node = frame[1] if frame[0] == "node" else frame[3]
                n, found = cost(node)
                total += n
                if found:
                    return total, True
            return total, False
        n, found = frame_cost(frames)
        return n if found else 10**9

    def reheap(self):
        self.queue = [((self.distance(frames), -seq) if self.policy == "distance"
                       else self.priority(state, seq), seq, fn, state, frames)
                      for _, seq, fn, state, frames in self.queue]
        heapq.heapify(self.queue)

    def set_policy(self, policy, preferences=None):
        if policy not in self.EXTRA_POLICIES + ("dfs", "random", "heuristic", "guided"):
            raise ValueError("unknown policy")
        self.policy = policy
        if preferences is not None:
            self.preferences = preferences
        self.reheap()

    def push(self, function, state, frames):
        if self.policy != "distance":
            return super().push(function, state, frames)
        if not frames or self.finding:
            return
        self.sequence += 1
        heapq.heappush(self.queue, ((self.distance(frames), -self.sequence), self.sequence,
                                    function, state, frames))

    def execute(self, fn, state, frames):
        if state.trace:
            edge = state.trace[-1]
            self.edge_visits[(edge["branch_id"], edge["visit"], edge["take"])] += 1
        super().execute(fn, state, frames)
        if self.policy == "coverage":
            self.reheap()

    def advance_event(self, extra_states=None, stop_on_failure=False):
        """Pause at the first new source-verification failure, without reset."""
        target = self.state_budget if extra_states is None else min(self.state_budget, self.visited + extra_states)
        start = len(self.failures)
        while self.queue and not self.finding and not self.stopped and self.visited < target:
            self.advance(extra_states=1)
            if stop_on_failure and len(self.failures) > start:
                return self.result(), self.failures[-1]
        return self.result(), None
