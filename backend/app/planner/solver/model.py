"""CP-SAT model of a degree plan.

Each unit gets one yes/no variable per term it may sit in. Prerequisites, credit
caps, duplicates, offering history and requirement coverage are constraints over
those variables. In check mode (`fixed=True`) every unit stays where it is, so the
model answers the same question as `validate()`: is this plan allowed as it stands?
Repair (repair.py) frees planned units, lets some be added or dropped, and puts the
request and saved settings behind assumption literals so a conflict can be explained.
"""

from dataclasses import dataclass, field
from typing import Literal

from ortools.sat.python import cp_model

from app.planner.audit import fill_order, needed
from app.planner.solver.units import Unit
from app.schemas.courses import AllOf, AnyOf, CourseReq, Flag, PrereqExpr
from app.schemas.requirements import Program, Requirement

Lit = cp_model.IntVar | bool
# audit: meet as many requirements as possible, then show as much progress as possible
# on the rest without spreading spare courses around
RequirementMode = Literal["off", "require", "maximize", "audit"]


@dataclass
class Options:
    fixed: bool = True  # every unit stays in its current term
    requirements: RequirementMode = "off"
    offerings: bool = False  # keep courses out of seasons they've never run in
    # only requirements: no prerequisites or credit caps (the audit, which has to say
    # what a broken plan covers too); a repeated course still counts once per rule
    requirements_only: bool = False
    # units the solver may leave out (open slots, candidates it may add)
    optional: frozenset[str] = frozenset()
    # top-level requirements that must stay met; repair keeps what the plan already meets
    keep_met: frozenset[str] | None = None
    # check completed and in-progress work too; repair can't change it, so it doesn't
    check_fixed: bool = True
    # put caps and kept requirements behind assumption literals, to explain a conflict
    explain: bool = False


@dataclass
class Result:
    status: Literal["feasible", "infeasible", "unknown"]
    terms: dict[str, str] = field(default_factory=dict)  # unit id -> term
    assigned: dict[str, list[str]] = field(default_factory=dict)  # requirement -> unit ids
    satisfied: set[str] = field(default_factory=set)  # requirement ids met (any level)
    # when infeasible with explain on: the assumptions that conflict
    core: list[tuple] = field(default_factory=list)
    optimal: bool = False
    objective: float | None = None
    values: dict[str, int] = field(default_factory=dict)  # the model's watched variables
    # units in the plan that earn no credit: a second copy, or a forbidden overlap
    no_credit: set[str] = field(default_factory=set)

    @property
    def feasible(self) -> bool:
        return self.status == "feasible"


def _named_only(r: Requirement) -> bool:
    """A rule made only of named course lists (the core, math), not filters."""
    if r.kind in ("all_of", "any_of"):
        return all(_named_only(c) for c in r.children)
    return r.kind == "courses"


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
        # assumption literal -> what it stands for, e.g. ("cap", "SP27")
        self.assumptions: dict[int, tuple] = {}
        self.guards: dict[tuple, cp_model.IntVar] = {}
        # extra variables a caller wants read back from the solution, by name
        self.watch: dict[str, cp_model.IntVar] = {}
        # requirement id -> group id -> (unit, "counted in this group") pairs
        self._group_count: dict[str, dict[str, list[tuple[Unit, cp_model.IntVar]]]] = {}
        self._guards: list[cp_model.IntVar] = []

        self._place()
        if not self.opts.requirements_only:
            self._prereqs()
            self._credits(max_credits, term_caps or {})
            self._duplicates()
        if self.opts.requirements != "off" or self.opts.keep_met is not None:
            self._requirements()

    def guard(self, key: tuple) -> cp_model.IntVar | None:
        """An assumption literal for one named constraint (None when not explaining)."""
        if not self.opts.explain:
            return None
        g = self.m.NewBoolVar(f"assume{key}")
        self.assumptions[g.Index()] = key
        self.guards[key] = g
        self._guards.append(g)
        return g

    @staticmethod
    def only_if(ct, g):
        if g is not None:
            ct.OnlyEnforceIf(g)
        return ct

    def credits_in(self, t: int):
        return sum(u.credits * self.x[u.id][t] for u in self.units if t in self.x[u.id])

    # where each unit may go ------------------------------------------------------

    def allowed(self, u: Unit) -> list[int]:
        if u.term not in self.index:
            # completed outside the plan's terms (AP or transfer credit) needs no slot;
            # a planned unit with no term yet (a candidate) may go in any future one
            if u.status != "planned" or self.opts.fixed:
                return []
        elif self.opts.fixed or u.fixed:
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
            if u.id not in self.opts.optional:
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
            elif len(earlier) == len(spots) and v.id not in self.opts.optional:
                lit = True  # it's in the plan and every spot it may take is earlier
            else:
                lit = self.m.NewBoolVar(f"before[{v.id},{t}]")
                self.m.Add(sum(earlier) == lit)
            self._before[key] = lit
        return self._before[key]

    def same_term(self, v: Unit, t: int) -> Lit:
        spots = self.x[v.id]
        if t not in spots:
            return False
        return True if len(spots) == 1 and v.id not in self.opts.optional else spots[t]

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
            if u.status != "planned" and not self.opts.check_fixed:
                continue  # already being taken; nothing a repair can change
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
            if not self.opts.check_fixed and all(u.status != "planned" for u, _ in here):
                continue  # past and current terms are what they are
            cap = caps[term] if term in caps else max_credits  # 0 means a term off
            g = self.guard(("cap", term, cap))
            self.only_if(self.m.Add(sum(u.credits * x for u, x in here) <= cap), g)

    def _duplicates(self):
        groups: dict[str, list[Unit]] = {}
        for u in self.units:
            if u.dup_key:
                groups.setdefault(u.dup_key, []).append(u)
        for group in groups.values():
            if len(group) < 2:
                continue
            # copies already taken stay (repeats are history); nothing more may be added
            planned = [self.present[u.id] for u in group if u.status == "planned"]
            if len(planned) < len(group):
                for p in planned:
                    self.m.Add(p == 0)
            else:
                self.m.AddAtMostOne(planned)

    # requirements ----------------------------------------------------------------

    def _credit_vars(self):
        """Whether each unit earns credit. Two copies of a course, or two courses the
        roster lists as forbidden overlaps ("no credit for both MATH 2210 and MATH
        2940"), earn it once between them; only a unit earning credit counts anywhere."""
        clashes = [
            (u, v)
            for i, u in enumerate(self.units)
            for v in self.units[i + 1 :]
            if u.dup_key and v.dup_key and (u.dup_key == v.dup_key or v.dup_key in u.no_credit_with)
        ]
        involved = {w.id for pair in clashes for w in pair}
        self.earns: dict[str, cp_model.IntVar] = {}
        for u in self.units:
            if u.id in involved:
                e = self.m.NewBoolVar(f"earns[{u.id}]")
                self.m.AddImplication(e, self.present[u.id])
                self.earns[u.id] = e
            else:
                self.earns[u.id] = self.present[u.id]
        for u, v in clashes:
            self.m.Add(self.earns[u.id] + self.earns[v.id] <= 1)
        self._clashing = [self.earns[i] for i in sorted(involved)]

    def _requirements(self):
        reqs = {r.id: r for r in self.program.all_requirements()}
        self._counted: dict[str, list[tuple[Unit, cp_model.IntVar]]] = {}
        self._leaf_sat: list[cp_model.IntVar] = []
        self._credit_vars()
        for u in self.units:
            for rid in u.eligible:
                a = self.m.NewBoolVar(f"a[{u.id},{rid}]")
                self.m.AddImplication(a, self.earns[u.id])
                self.a[(u.id, rid)] = a
                self._counted.setdefault(rid, []).append((u, a))
            # one requirement per unit, except pairs the rules allow to share
            for i, r1 in enumerate(u.eligible):
                for r2 in u.eligible[i + 1 :]:
                    if not self._may_share(u, reqs[r1], reqs[r2]):
                        self.m.Add(self.a[(u.id, r1)] + self.a[(u.id, r2)] <= 1)

        for rid, counted in self._counted.items():
            self._subject_rules(reqs[rid], counted)
            self._group_rules(reqs[rid], counted)

        tops = []
        self._tops = [r for s in self.program.sets for r in s.requirements]
        for top in self._tops:
            lit = self._req_sat(top)
            tops.append(lit)
            keep = self.opts.keep_met is not None and top.id in self.opts.keep_met
            if (self.opts.requirements == "require" or keep) and lit is not True:
                g = self.guard(("met", top.id)) if keep else None
                if lit is False:
                    self.only_if(self.m.AddBoolOr([]), g)  # can't be met at all
                else:
                    self.only_if(self.m.Add(lit == 1), g)

        if self.opts.requirements == "maximize":
            # whole top-level rules first; met leaves only break ties, so the model
            # won't trade half of an all_of for some other leaf
            weight = len(self._leaf_sat) + 1
            self.m.Maximize(weight * sum(tops) + sum(self._leaf_sat))
        elif self.opts.requirements == "audit":
            self._audit_objective(tops, reqs)

    def _audit_objective(self, tops: list[Lit], reqs: dict[str, Requirement]):
        """Named course lists first (whole rules, then each course on a list), then whole
        rules, then met leaves, then progress on unmet ones (a course counts as progress
        only up to what the rule needs), and no spare assignments: a course that isn't
        needed anywhere stays unassigned."""
        every = [a for pairs in self._counted.values() for _, a in pairs]
        progress = []
        named_progress = []  # courses counted on a named list ("CS 3110"), up to its need
        for rid, pairs in self._counted.items():
            p = self.m.NewIntVar(0, needed(reqs[rid]), f"progress[{rid}]")
            self.m.Add(p <= sum(a for _, a in pairs))
            progress.append(p)
            if reqs[rid].kind == "courses":
                named_progress.append(p)
        w_progress = 2
        w_leaf = w_progress * len(every) + len(every) + 1
        # between plans meeting as many rules, prefer meeting the specific ones (ENGRI,
        # liberal studies) over catch-all electives, which any spare course can fill
        specific = [lit for lit, top in zip(tops, self._tops, strict=True) if fill_order(top) < 2]
        w_specific = w_leaf * (len(self._leaf_sat) + 1) + w_progress * len(every) + 1
        w_top = w_specific * (len(specific) + 1)
        # a course on a named list (the core, math) counts there before it fills a broad
        # elective, even when that leaves the elective short: the elective can take any of
        # many other courses, so an unfinished plan shows its gap where a slot can fill it
        named = [lit for lit, top in zip(tops, self._tops, strict=True) if _named_only(top)]
        w_named_course = w_top * (len(tops) + 1)
        most = sum(needed(reqs[rid]) for rid in self._counted if reqs[rid].kind == "courses")
        w_named = w_named_course * (most + 1)
        # last of all, credit for as many units as the overlaps allow, so the reported
        # credit total is the most the plan can earn
        w_rules = len(self._clashing) + 1
        self.m.Maximize(
            w_rules
            * (
                w_named * sum(named)
                + w_named_course * sum(named_progress)
                + w_top * sum(tops)
                + w_specific * sum(specific)
                + w_leaf * sum(self._leaf_sat)
                + w_progress * sum(progress)
                - sum(every)
            )
            + sum(self._clashing)
        )

    def _may_share(self, u: Unit, r1: Requirement, r2: Requirement) -> bool:
        """Whether one course may count toward both rules: double_count allows the pair,
        and the course isn't one of the rules' exceptions to it."""
        if r2.id not in r1.double_count and r1.id not in r2.double_count:
            return False
        barred = set(r1.double_count_except.get(r2.id, [])) | set(
            r2.double_count_except.get(r1.id, [])
        )
        return u.course not in barred

    def _group_rules(self, r: Requirement, counted: list[tuple[Unit, cp_model.IntVar]]):
        """Category rules inside one requirement: each counted course is placed in one of
        its groups, or up to `groups_per_course` of them (an open slot in any), groups
        can be capped, and the rule's satisfaction lit later requires enough distinct
        groups and per-group credits."""
        if r.groups:
            ids = [g.id for g in r.groups]
            per = r.groups_per_course
            place: dict[str, list[tuple[Unit, cp_model.IntVar]]] = {g: [] for g in ids}
            multi: list[cp_model.IntVar] = []  # courses covering more than one group
            for u, a in counted:
                mine = ids if u.course is None else sorted(u.groups.get(r.id, ()))
                if not mine:
                    self.m.Add(a == 0)  # a course outside every group can't count here
                    continue
                bs = [self.m.NewBoolVar(f"g[{u.id},{r.id},{g}]") for g in mine]
                if per == 1 or len(bs) == 1:
                    self.m.Add(sum(bs) == a)
                else:
                    # counted: in at least one of its groups and at most `per`; not
                    # counted: in none
                    self.m.Add(sum(bs) >= a)
                    self.m.Add(sum(bs) <= per * a)
                    if r.max_multi_group_courses is not None:
                        # covering a second group uses one of the rule's allowances
                        extra = self.m.NewBoolVar(f"multi[{u.id},{r.id}]")
                        self.m.Add(sum(bs) <= a + (per - 1) * extra)
                        multi.append(extra)
                for g, b in zip(mine, bs, strict=True):
                    place[g].append((u, b))
            if r.max_multi_group_courses is not None and len(multi) > r.max_multi_group_courses:
                self.m.Add(sum(multi) <= r.max_multi_group_courses)
            for g in r.groups:
                if g.max_courses is not None and len(place[g.id]) > g.max_courses:
                    self.m.Add(sum(b for _, b in place[g.id]) <= g.max_courses)
            self._group_count[r.id] = place
        for level, cap in r.max_below_level.items():
            below = [a for u, a in counted if u.course is not None and (u.level or 0) < level]
            if len(below) > cap:
                self.m.Add(sum(below) <= cap)

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
        elif r.kind == "total_credits":
            here = [u for u in self.units if r.id in u.totals]
            lit = self.m.NewBoolVar(f"sat[{r.id}]")
            total = sum(u.credits * self.earns[u.id] for u in here)
            self.m.Add(total >= (r.credits or 0)).OnlyEnforceIf(lit)
            self._leaf_sat.append(lit)
        else:
            counted = self._counted.get(r.id, [])
            lit = self.m.NewBoolVar(f"sat[{r.id}]")
            self.m.Add(sum(a for _, a in counted) >= needed(r)).OnlyEnforceIf(lit)
            if r.credits:
                self.m.Add(sum(u.credits * a for u, a in counted) >= r.credits).OnlyEnforceIf(lit)
            for level, n in r.min_at_level.items():
                # an open slot may still become a course at that level
                up = [a for u, a in counted if u.course is None or (u.level or 0) >= level]
                self.m.Add(sum(up) >= n).OnlyEnforceIf(lit)
            place = self._group_count.get(r.id)
            if place is not None:
                covered = []
                for g in r.groups:
                    cell = place[g.id]
                    if g.min_credits:
                        got = sum(u.credits * b for u, b in cell)
                        self.m.Add(got >= g.min_credits).OnlyEnforceIf(lit)
                    c = self.m.NewBoolVar(f"covered[{r.id},{g.id}]")
                    self.m.Add(c <= sum(b for _, b in cell))
                    covered.append(c)
                if r.min_groups:
                    self.m.Add(sum(covered) >= r.min_groups).OnlyEnforceIf(lit)
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

    def solve(
        self,
        time_limit: float = 2.0,
        seed: int = 0,
        *,
        assume: list[cp_model.IntVar] | None = None,
        first_solution: bool = False,
    ) -> Result:
        """`assume` replaces the full set of assumptions (to test a smaller conflict);
        `first_solution` stops as soon as any plan is found (a feasibility check)."""
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1  # reproducible for the evaluation
        solver.parameters.random_seed = seed
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.stop_after_first_solution = first_solution
        # LP reasoning over the credit and requirement sums; without it, proving that a
        # tight request is impossible can take longer than the time limit
        solver.parameters.linearization_level = 2
        guards = self._guards if assume is None else assume
        self.m.ClearAssumptions()
        if guards:
            self.m.AddAssumptions(guards)
        code = solver.Solve(self.m)
        if code == cp_model.INFEASIBLE:
            core = solver.SufficientAssumptionsForInfeasibility() if guards else []
            return Result(
                "infeasible", core=[self.assumptions[i] for i in core if i in self.assumptions]
            )
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
        objective = solver.ObjectiveValue() if self.m.HasObjective() else None
        return Result(
            "feasible",
            terms,
            assigned,
            satisfied,
            optimal=code == cp_model.OPTIMAL,
            objective=objective,
            values={name: solver.Value(v) for name, v in self.watch.items()},
            no_credit={
                uid
                for uid, e in getattr(self, "earns", {}).items()
                if e is not self.present[uid] and solver.Value(self.present[uid]) and not value(e)
            },
        )
