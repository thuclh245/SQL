from enum import Enum

class NextAction(str, Enum):
    ANSWER = "answer"
    ABSTAIN = "abstain"
    AMBIGUOUS = "ambiguous"
    EXPAND_SCHEMA = "expand_schema"
    PROBE_VALUE = "probe_value"
    REPAIR_SQL = "repair_sql"
    ALTERNATIVE_SOLVER = "alternative_solver"
    SEMANTIC_VERIFY = "semantic_verify"

async def run_query(state, deps):
    state.scope = await deps.auth.resolve_scope(state.user)
    state.grounding = await deps.grounding.build(state.request, state.scope)

    while True:
        candidate = await deps.solver.generate(state)
        state.candidates.append(candidate)

        report = await deps.verifier.verify(state, candidate)
        state.findings.extend(report.findings)

        if report.has_block:
            action = deps.risk.next_action(state)
        else:
            obs = await deps.db.explain(state.db_context(), candidate.sql)
            state.db_observations.append(obs)
            action = deps.risk.next_action(state)

        if action is NextAction.ANSWER:
            result = await deps.db.execute(state.db_context(), candidate.sql)
            return deps.response.answer(state, candidate, result)
        if action is NextAction.ABSTAIN:
            return deps.response.abstain(state)
        if action is NextAction.AMBIGUOUS:
            return deps.response.ambiguous(state)

        if not state.budget_allows(action):
            return deps.response.abstain(state, reason="budget_exhausted")

        await deps.recovery.apply(action, state)
        state.consume_budget(action)
