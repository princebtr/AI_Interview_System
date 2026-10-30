"""Helpers for the Batch -> Department -> Section -> Cohort tree.

Every lookup is scoped to one institution, so a tenant can never read or
reference another tenant's groups.
"""
from django.core.exceptions import ValidationError

from accounts.models import User
from config.http import BadRequest

from .models import ANCESTORS, LEVEL_LABELS, LEVELS, MODELS, path_dict

# The level below each level, and the related name that reaches it.
CHILD_LEVEL = dict(zip(LEVELS, LEVELS[1:]))
CHILDREN = {"batch": "departments", "department": "sections", "section": "cohorts"}
PARENT_LEVEL = {child: parent for parent, child in CHILD_LEVEL.items()}
MAX_NAME = 60
EMPTY_STATS = {"studentCount": 0, "activated": 0, "attempts": 0, "practice30Days": 0, "averageScore": None}


def find_node(institution, level, node_id):
    """This institution's group at `level` with that id, or None."""
    if not isinstance(level, str) or level not in MODELS or not isinstance(node_id, str) or not node_id.strip():
        return None
    try:
        return (
            MODELS[level]
            .objects.select_related(*ANCESTORS[level])
            .filter(institution=institution, pk=node_id.strip())
            .first()
        )
    except ValidationError:  # not a valid ObjectId
        return None


def filter_by_groups(queryset, institution, params):
    """Narrow a User queryset by any of the ?batch=&department=&section=&cohort= ids."""
    for level in LEVELS:
        node_id = params.get(level, "").strip()
        if node_id:
            node = find_node(institution, level, node_id)
            if node is None:
                raise BadRequest(f"Unknown {level}")
            queryset = queryset.filter(**{level: node})
    return queryset


def clean_name(raw, level):
    """A tidy group name, or raise BadRequest with a field error."""
    noun = LEVEL_LABELS[level].lower()
    name = MODELS[level].clean_name(raw) if isinstance(raw, str) else ""
    if not name:
        message = f"Enter a {noun} name"
    elif len(name) > MAX_NAME:
        message = f"{LEVEL_LABELS[level]} names can be at most {MAX_NAME} characters"
    else:
        return name
    raise BadRequest(message, [{"field": "name", "message": message}])


def sibling_filter(level, parent, institution):
    """Filter selecting the groups that share a parent (where names must be unique)."""
    return {PARENT_LEVEL[level]: parent} if parent is not None else {"institution": institution}


def node_summary(node, stats, lineage=None):
    """The node's place in the tree and its stats (from ai.stats.group_stats)."""
    return {
        **path_dict(lineage or node.lineage()),
        "createdAt": node.created_at,
        **stats.get((node.LEVEL, node.pk), EMPTY_STATS),
    }


def tree(institution, stats):
    """Every batch with its departments, sections and cohorts nested under
    `children`, sorted by name, each with its stats. Four queries in all."""
    nodes = {level: list(MODELS[level].objects.filter(institution=institution)) for level in LEVELS}
    children = {level: {} for level in LEVELS}
    for level in LEVELS[1:]:
        parent_field = f"{PARENT_LEVEL[level]}_id"
        for node in nodes[level]:
            children[level].setdefault(getattr(node, parent_field), []).append(node)

    def build(node, lineage):
        lineage = [*lineage, node]
        entry = node_summary(node, stats, lineage)
        child_level = CHILD_LEVEL.get(node.LEVEL)
        if child_level:
            entry["children"] = [build(c, lineage) for c in children[child_level].get(node.pk, [])]
        return entry

    return [build(batch, []) for batch in nodes["batch"]]


PLURALS = {"batch": "batches", "department": "departments", "section": "sections", "cohort": "cohorts"}


def counts(institution):
    """{batches, departments, sections, cohorts}: how many groups of each level."""
    return {PLURALS[level]: MODELS[level].objects.filter(institution=institution).count() for level in LEVELS}


def student_counts(institution):
    """{(level, pk): number of students} for every group, at every level, in one pass."""
    sizes = {}
    students = User.objects.filter(institution=institution, role="student", cohort__isnull=False)
    for ids in students.values_list(*(f"{level}_id" for level in LEVELS)):
        for key in zip(LEVELS, ids):
            sizes[key] = sizes.get(key, 0) + 1
    return sizes
