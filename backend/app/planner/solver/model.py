"""CP-SAT model of a degree plan.

Each unit gets one yes/no variable per term it may sit in. Prerequisites, credit
caps, duplicates, offering history and requirement coverage are constraints over
those variables. In check mode (`fixed=True`) every unit stays where it is, so the
model answers the same question as `validate()`: is this plan allowed as it stands?
Repair (next milestone) frees planned units and adds an objective.
"""

from dataclasses import dataclass, field
from typing import Literal

from ortools.sat.python import cp_model

from app.planner.audit import needed
from app.planner.solver.units import Unit
from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag, PrereqExpr
from app.schemas.requirements import Program, Requirement

Lit = cp_model.IntVar | bool
RequirementMode = Literal["off", "require", "maximize"]


@dataclass
class Options:
    fixed: bool = True  # every unit stays in its current term
    requirements: RequirementMode = "off"
    offerings: bool = False  # keep courses out of seasons they've never run in


@dataclass
class Result:
    status: Literal["feasible", "infeasible", "unknown"]
    terms: dict[str, str] = field(default_factory=dict)  # unit id -> term
    assigned: dict[str, list[str]] = field(default_factory=dict)  # requirement -> unit ids
    satisfied: set[str] = field(default_factory=set)  # requirement ids met (any level)

    @property
    def feasible(self) -> bool:
        return self.status == "feasible"


class PlanModel:
    def __init__(
        self,
        units: list[Unit],
        terms: list[str],
        current_term: str,
        program: Program,
        *,
        max_credits: int = 18,
        term_caps: dict[str, int] | None = None,
        options: Options | None = None,
    ):
        self.units = units
        self.terms = terms
        self.program = program
        self.opts = options or Options()
        self.m = cp_model.CpModel()
        self.index = {t: i for i, t in enumerate(terms)}
        self.now = self.index.get(current_term, 0)
        self.x: dict[str, dict[int, cp_model.IntVar]] = {}
        self.present: dict[str, cp_model.IntVar] = {}
        self.sat: dict[str, Lit] = {}
        self.a: dict[tuple[str, str], cp_model.IntVar] = {}
        self._before: dict[tuple[str, int], Lit] = {}

        self._place()
        self._prereqs()
        self._credits(max_credits, term_caps or {})
        self._duplicates()
        if self.opts.requirements != "off":
            self._requirements()

    # where each unit may go ------------------------------------------------------

    def allowed(self, u: Unit) -> list[int]:
        if u.term not in self.index:
            # completed outside the plan's terms (AP or transfer credit) needs no slot;
            # anything else there can't be placed
            return []
        if self.opts.fixed or u.fixed:
            return [self.index[u.term]]
        options = range(self.now + 1, len(self.terms))
        if self.opts.offerings and u.seasons:
            options = [t for t in options if self.terms[t][:2] in u.seasons]
        return list(options)

    def _place(self):
        for u in self.units:
            spots = self.allowed(u)
            self.x[u.id] = {t: self.m.NewBoolVar(f"x[{u.id},{t}]") for t in spots}
            self.present[u.id] = self.m.NewBoolVar(f"present[{u.id}]")
            if not spots and u.status == "completed":
                self.m.Add(self.present[u.id] == 1)  # outside the terms but done
                continue
            self.m.Add(sum(self.x[u.id].values()) == self.present[u.id])
            # every unit in the plan stays in it; repair will relax this for removable ones
            self.m.Add(self.present[u.id] == 1)

    # prerequisites ---------------------------------------------------------------

    def before(self, v: Unit, t: int) -> Lit:
        """v counts as taken before term t (completed anywhere, or in an earlier term)."""
        if v.status == "completed":
            return True
        key = (v.id, t)
        if key not in self._before:
            spots = self.x[v.id]
            earlier = [x for s, x in spots.items() if s < t]
            if not earlier:
                lit: Lit = False
            elif len(earlier) == len(spots):
                lit = True  # every spot it may take is earlier
            else:
                lit = self.m.NewBoolVar(f"before[{v.id},{t}]")
                self.m.Add(sum(earlier) == lit)
            self._before[key] = lit
        return self._before[key]

    def same_term(self, v: Unit, t: int) -> Lit:
        spots = self.x[v.id]
        if t not in spots:
            return False
        return True if len(spots) == 1 else spots[t]

    def _sat(self, expr: PrereqExpr | None, u: Unit, t: int) -> Lit:
        match expr:
            case None | Flag():
                return True  # flags are left to a person, as in validate()
            case CourseReq():
                options = []
                for v in self.units:
                    if v.id != u.id and expr.code in v.credit_for:
                        options.append(self.before(v, t))
                        if expr.concurrent:
                            options.append(self.same_term(v, t))
                return self._or(options)
            case AllOf():
                return self._and([self._sat(e, u, t) for e in expr.items])
            case AnyOf():
                return self._or([self._sat(e, u, t) for e in expr.items])
        return True

    def _prereqs(self):
        for u in self.units:
            if u.status == "completed" or u.prereqs is None:
                continue
            for t, x in self.x[u.id].items():
                lit = self._sat(u.prereqs, u, t)
                if lit is False:
                    self.m.Add(x == 0)
                elif lit is not True:
                    self.m.AddImplication(x, lit)

    # credits and duplicates ------------------------------------------------------

    def _credits(self, max_credits: int, caps: dict[str, int]):
        for t, term in enumerate(self.terms):
            here = [(u, self.x[u.id][t]) for u in self.units if t in self.x[u.id]]
            # like validate(): a term holding only completed work isn't capped
            if not here or all(u.status == "completed" for u, _ in here):
                continue
            cap = caps.get(term) or max_credits
            self.m.Add(sum(u.credits * x for u, x in here) <= cap)

    def _duplicates(self):
        groups: dict[str, list[Unit]] = {}
        for u in self.units:
            if u.dup_key:
                groups.setdefault(u.dup_key, []).append(u)
        for group in groups.values():
            if len(group) > 1:
                self.m.AddAtMostOne(self.present[u.id] for u in group)

    # requirements ----------------------------------------------------------------

    def _requirements(self):
        reqs = {r.id: r for r in self.program.all_requirements()}
        self._counted: dict[str, list[tuple[Unit, cp_model.IntVar]]] = {}
        self._leaf_sat: list[cp_model.IntVar] = []
        for u in self.units:
            for rid in u.eligible:
                a = self.m.NewBoolVar(f"a[{u.id},{rid}]")
                self.m.AddImplication(a, self.present[u.id])
                self.a[(u.id, rid)] = a
                self._counted.setdefault(rid, []).append((u, a))
            # one requirement per unit, except pairs the rules allow to share
            for i, r1 in enumerate(u.eligible):
                for r2 in u.eligible[i + 1 :]:
                    if r2 not in reqs[r1].double_count and r1 not in reqs[r2].double_count:
                        self.m.Add(self.a[(u.id, r1)] + self.a[(u.id, r2)] <= 1)

        for rid, counted in self._counted.items():
            self._subject_rules(reqs[rid], counted)

        tops = []
        for top in (r for s in self.program.sets for r in s.requirements):
            lit = self._req_sat(top)
            tops.append(lit)
            if self.opts.requirements == "require" and lit is not True:
                if lit is False:
                    self.m.Add(self.m.NewConstant(0) == 1)
                else:
                    self.m.Add(lit == 1)

        if self.opts.requirements == "maximize":
            # whole top-level rules first; met leaves only break ties, so the model
            # won't trade half of an all_of for some other leaf
            weight = len(self._leaf_sat) + 1
            self.m.Maximize(weight * sum(tops) + sum(self._leaf_sat))

    def _subject_rules(self, r: Requirement, counted: list[tuple[Unit, cp_model.IntVar]]):
        for subject, cap in r.max_cross_listed.items():
            crossed = [a for u, a in counted if subject in u.cross_listed]
            if len(crossed) > cap:
                self.m.Add(sum(crossed) <= cap)
        if not r.same_subject:
            return
        # pick one subject for the rule; every course counted must carry it (an open
        # slot has no course yet, so it fits whichever subject is picked)
        courses = [(u, a) for u, a in counted if u.course is not None]
        subjects = sorted({s for u, _ in courses for s in u.subjects})
        if len(subjects) <= 1:
            return
        pick = {s: self.m.NewBoolVar(f"subject[{r.id},{s}]") for s in subjects}
        self.m.AddAtMostOne(pick.values())
        for u, a in courses:
            self.m.AddBoolOr([pick[s] for s in sorted(u.subjects)]).OnlyEnforceIf(a)

    def _req_sat(self, r: Requirement) -> Lit:
        if r.kind == "flag_only":
            lit: Lit = True  # needs a person's sign-off; never blocks a plan
        elif r.kind in ("all_of", "any_of"):
            kids = [self._req_sat(c) for c in r.children]
            lit = self._and(kids) if r.kind == "all_of" else self._or(kids)
        else:
            counted = self._counted.get(r.id, [])
            lit = self.m.NewBoolVar(f"sat[{r.id}]")
            self.m.Add(sum(a for _, a in counted) >= needed(r)).OnlyEnforceIf(lit)
            if r.credits:
                self.m.Add(sum(u.credits * a for u, a in counted) >= r.credits).OnlyEnforceIf(lit)
            self._leaf_sat.append(lit)
        self.sat[r.id] = lit
        return lit

    # boolean helpers -------------------------------------------------------------

    def _or(self, lits: list[Lit]) -> Lit:
        if any(lit is True for lit in lits):
            return True
        lits = [lit for lit in lits if lit is not False]
        if not lits:
            return False
        if len(lits) == 1:
            return lits[0]
        b = self.m.NewBoolVar("")
        self.m.AddMaxEquality(b, lits)
        return b

    def _and(self, lits: list[Lit]) -> Lit:
        if any(lit is False for lit in lits):
            return False
        lits = [lit for lit in lits if lit is not True]
        if not lits:
            return True
        if len(lits) == 1:
            return lits[0]
        b = self.m.NewBoolVar("")
        self.m.AddMinEquality(b, lits)
        return b

    # solving ---------------------------------------------------------------------

    def solve(self, time_limit: float = 2.0, seed: int = 0) -> Result:
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1  # reproducible for the evaluation
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = time_limit
        code = solver.Solve(self.m)
        if code == cp_model.INFEASIBLE:
            return Result("infeasible")
        if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return Result("unknown")

        def value(lit: Lit) -> bool:
            return lit if isinstance(lit, bool) else bool(solver.Value(lit))

        terms = {
            uid: self.terms[t]
            for uid, spots in self.x.items()
            for t, x in spots.items()
            if solver.Value(x)
        }
        assigned: dict[str, list[str]] = {}
        for (uid, rid), a in self.a.items():
            if solver.Value(a):
                assigned.setdefault(rid, []).append(uid)
        satisfied = {rid for rid, lit in self.sat.items() if value(lit)}
        return Result("feasible", terms, assigned, satisfied)
