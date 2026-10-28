"""Explicit registry of trusted update workflows."""

from . import general, all_als

WORKFLOWS = {'general': general, 'all_als': all_als}


def get_workflow(name):
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise ValueError(f"Unknown update workflow {name!r}; choose from {', '.join(WORKFLOWS)}") from None
