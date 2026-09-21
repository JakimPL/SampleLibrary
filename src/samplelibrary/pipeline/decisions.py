from __future__ import annotations

from dataclasses import replace

from samplelibrary.pipeline.artifacts import read_step_record
from samplelibrary.pipeline.context import PipelineContext
from samplelibrary.pipeline.results import StepAction, StepPlan, changed_components
from samplelibrary.pipeline.steps.kinds import Step, StepRefused


def decide(context: PipelineContext, step: Step) -> StepPlan:
    """What a step says is left to do about itself now, which a run acts on and `status` reports.

    A step with work left names why: the reason it gives itself, or else the inputs that read
    differently than when it last finished. A step whose inputs cannot be read as it needs them
    refuses, naming what a person settles first.
    """
    try:
        plan = step.evaluate(context)
    except StepRefused as refusal:
        return StepPlan(inputs={}, action=StepAction.REFUSE, reason=str(refusal))
    if plan.action not in (StepAction.RUN, StepAction.SEAL) or plan.reasons:
        return plan
    recorded = read_step_record(context.layout.step_record(step.name))
    if recorded is None:
        return plan
    return replace(plan, reasons=changed_components(plan.inputs, recorded.inputs))
