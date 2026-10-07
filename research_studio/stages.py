"""Single executable StageSpec: roles, outputs, duty and allowed transitions."""
from dataclasses import dataclass, asdict
from .version import WORKFLOW_VERSION
from .util import require, identity

@dataclass(frozen=True)
class StageSpec:
    phase: str
    duty: str
    roles: tuple[str, ...]
    outputs: tuple[str, ...]
    independent_roles: tuple[str, ...] = ()
    normal_next: str | None = None
    context_kinds: tuple[str, ...] = ()

_ROWS = [
 ("P0", "Freeze the original problem, materials, scope and authorization", ("PLAN",), ("problem",)),
 ("P1", "Fix objects, hypotheses, quantifiers and notation", ("PLAN",), ("definition","problem","gap")),
 ("P2", "Derive necessary, sufficient or equivalent target requirements", ("PLAN",), ("requirement","route","gap")),
 ("P3", "Select a justified route and the first verifiable task", ("PLAN",), ("route","gap")),
 ("P4", "Perform actual derivation, construction and scoped failure analysis", ("RESEARCH",), ("result","attempt","failure","gap")),
 ("P5", "Compare obtained conclusions with exact target requirements", ("SYNTHESIS",), ("gap","requirement")),
 ("P6", "Prove AND/OR reductions, retaining lifting and compatibility duties", ("PLAN",), ("subproblem","reduction","gap")),
 ("P7", "Reconstruct methods and derive independently, then synthesize", ("LEARN","DIRECT","SYNTHESIS"), ("study","transfer","result","failure","gap")),
 ("P8", "Execute dependency-bound proof repair and failure-driven falsification", ("RESEARCH","FALSIFY","SYNTHESIS"), ("result","attempt","failure","gap")),
 ("P9", "Independent global proof and counterexample audit, then synthesize", ("PROOF","COUNTEREXAMPLE","SYNTHESIS"), ("review","gap","failure")),
 ("P10", "Assemble the framework with exact same-witness compatibility", ("SYNTHESIS",), ("framework","gap")),
 ("P11", "Account for genuine change and all outstanding duties", ("SYNTHESIS",), ("progress","gap")),
 ("P12", "Independently check the assembled framework and open boundary", ("INDEPENDENT",), ("review","gap")),
 ("P13", "Lecture first, independently reviewed, then same-source minimal", ("REPORT_AUTHOR","REPORT_SEMANTIC","REPORT_VISUAL"), ("report","report_review")),
 ("P14", "Wait for the researcher's explicit decision bound to this delivery", (), ()),
]
CONTEXT = (
 ('problem',), ('problem','definition'), ('problem','definition'),
 ('problem','requirement','route'), ('problem','requirement','route','result'),
 ('problem','requirement','result'), ('problem','requirement','gap'),
 ('problem','subproblem','reduction','gap','failure'),
 ('problem','subproblem','reduction','gap','failure','result'),
 ('problem','reduction','result','failure'),
 ('problem','result','reduction','gap','review'),
 ('problem','framework','gap','progress'),
 ('problem','framework','result','reduction','gap'), (), ())
STAGES = {row[0]: StageSpec(*row,
    independent_roles=("PROOF","COUNTEREXAMPLE") if row[0]=="P9" else ("INDEPENDENT",) if row[0]=="P12" else (),
    normal_next="P"+str(i+1) if i<14 else None,
    context_kinds=CONTEXT[i]) for i,row in enumerate(_ROWS)}

def spec(phase):
    require(phase in STAGES, "PHASE_INVALID", str(phase))
    return STAGES[phase]

def definition():
    return {"version": WORKFLOW_VERSION, "stages": [asdict(s) for s in STAGES.values()],
            "early_delivery": "P0-P12 to P13 preserves unperformed work",
            "completion_is_not_proof": True}

def digest():
    return identity(definition())

def allowed(source, target):
    spec(source); spec(target)
    return (target == spec(source).normal_next or
            source != "P14" and target == "P13" or
            source not in ("P13", "P14") and 1 <= int(target[1:]) <= int(source[1:]))

def validate_structure(phase, records):
    for obj in records:
        require(obj["kind"] in spec(phase).outputs, "STAGE_OUTPUT_FORBIDDEN", obj["kind"])
        d = obj.get("data", {})
        if obj["kind"] == "reduction":
            require(d.get("operator") in ("AND", "OR") and d.get("children")
                    and d.get("lifting_obligations") and d.get("compatibility_obligations")
                    and isinstance(d.get("additional_hypotheses"), list),
                    "REDUCTION_INCOMPLETE", "P6 requires children, logic, hypotheses, lifting and compatibility duties")
        if obj['kind'] == 'failure':
            require(all(d.get(k) for k in ('mechanism','preserved_hypotheses','scope','realization_test'))
                    and d.get('disposition') in ('FALSIFY','PROOF_REPAIR','DEFER','NOT_ACTIONABLE'),
                    'FAILURE_SCOPE_REQUIRED','Preserve the failed implication, assumptions, realization test and scope')
        if obj["kind"] == "framework":
            require(isinstance(d.get("components"),list) and isinstance(d.get("same_witness"),dict)
                    and d["same_witness"].get("status") in ("OPEN","CONDITIONAL","CHECKED_CANDIDATE"),
                    "SAME_WITNESS_REQUIRED", "Independent existence statements do not supply a common witness")
            if d["same_witness"]["status"] == "CHECKED_CANDIDATE":
                require(d["same_witness"].get("evidence_refs"), "WITNESS_EVIDENCE_REQUIRED", "Exact compatibility evidence is required")


def role_allowed(phase, role):
    return role in spec(phase).roles or role == 'TASK_CHECK' and phase not in ('P13','P14') or role == 'SPECIALIST' and phase == 'P9'


def output_allowed(phase, role, kind):
    if role == 'TASK_CHECK': return kind == 'work_review'
    if role in ('REPORT_SEMANTIC','REPORT_VISUAL'): return kind == 'report_review'
    if role == 'REPORT_AUTHOR': return kind == 'report'
    if role in ('PROOF','COUNTEREXAMPLE','INDEPENDENT','SPECIALIST'):
        return kind in ('review','gap','failure')
    return kind in spec(phase).outputs


def validate_completion(phase, target, records):
    """Forward gates cannot replace an actual reduction/framework with a label."""
    if target != spec(phase).normal_next:return
    kinds={o['kind'] for o in records}
    required={'P6':'reduction','P10':'framework'}.get(phase)
    require(required is None or required in kinds,'STAGE_PRODUCT_MISSING',
            'Forward progression requires the substantive '+str(required)+' product; early delivery remains available')
