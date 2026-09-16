from typing import Protocol

from t2s.contracts import SqlCandidate
from t2s.solver.solver_request import SolverRequest


class SolverPort(Protocol):
    async def generate_sql_candidate(self, solver_request: SolverRequest) -> SqlCandidate: ...
