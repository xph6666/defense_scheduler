"""Natural order of inherited group numbers (G2 before G10)."""
import re


def group_order_key(group_id):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r'(\d+)', str(group_id)))


def finalize_pre_group_numbers(groups):
    """Assign initial public numbers once, after pre-defense optimization.

    Only new in-memory plans may call this. Saved groups keep their identities.
    Returns the chronological drafts and the provisional-to-final name map.
    """
    ordered = sorted(groups, key=lambda g: (g.time_slot is None,
                                            g.time_slot.start if g.time_slot else 0,
                                            group_order_key(g.group_id)))
    names = {g.group_id: f'G{i:03}' for i, g in enumerate(ordered, 1)}
    for g in ordered:
        g.group_id = names[g.group_id]
    return ordered, names
