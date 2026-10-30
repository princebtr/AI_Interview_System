"""Institution administration: members (users) and the academic structure
(Batch -> Department -> Section -> Cohort).

Every query is scoped to the requesting user's institution, so one tenant can
never read or reference another tenant's records.
"""
import csv
import io

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts import validators as v
from accounts.auth import jwt_required, role_required
from accounts.models import User
from accounts.passwords import generate_password, hash_many
from accounts.throttle import clear_attempts, throttle_key
from ai import stats
from ai.models import PracticeAttempt
from config.csvfile import read_csv, safe_cell
from config.http import BadRequest, api_view, clean_query, error, json_body

from . import validators as institution_rules
from .branding import process_logo
from . import structure
from .models import ANCESTORS, LEVEL_LABELS, LEVELS, MODELS, AuditLog, Cohort, Institution
from .theme import theme_dict

ROLES = [role for role, _ in User.ROLE_CHOICES]
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_SEARCH_LEN = 100
MAX_OFFSET = 1_000_000
MAX_IMPORT_ROWS = 500
MAX_IMPORT_BYTES = 1024 * 1024
ROLE_LABELS = dict(User.ROLE_CHOICES)


def find_member(institution, user_id):
    """This institution's user with that id, or None."""
    try:
        return (
            User.objects.filter(institution=institution, pk=user_id)
            .select_related(*User.PLACEMENT_FIELDS)
            .first()
        )
    except ValidationError:
        return None


def member_dict(user):
    return {
        "id": str(user.pk),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "cohort": user.cohort.to_dict() if user.cohort_id else None,
        "placement": user.placement(),
        "mustChangePassword": user.must_change_password,
        "lastLogin": user.last_login,
        "createdAt": user.created_at,
    }


def find_cohort(institution, cohort_id):
    """This institution's cohort with that id (ancestors loaded), or None."""
    return structure.find_node(institution, "cohort", cohort_id)


def parse_int(raw, default, *, low, high=None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    value = max(low, value)
    return min(high, value) if high is not None else value


# --------------------------------------------------------------------------- #
# Users                                                                        #
# --------------------------------------------------------------------------- #


def list_users(request):
    institution = request.user.institution
    members = User.objects.filter(institution=institution)
    counts = {role: members.filter(role=role).count() for role in ROLES}

    role = request.GET.get("role", "").strip()
    if role:
        if role not in ROLES:
            raise BadRequest("Unknown role filter")
        members = members.filter(role=role)

    members = structure.filter_by_groups(members, institution, request.GET)

    query = clean_query(request.GET.get("q"), MAX_SEARCH_LEN)
    if query:
        members = members.filter(Q(name__icontains=query) | Q(email__icontains=query))

    total = members.count()
    offset = parse_int(request.GET.get("offset"), 0, low=0, high=MAX_OFFSET)
    limit = parse_int(request.GET.get("limit"), DEFAULT_PAGE_SIZE, low=1, high=MAX_PAGE_SIZE)
    page = members.select_related(*User.PLACEMENT_FIELDS).order_by("-created_at")[offset : offset + limit]

    return JsonResponse(
        {"users": [member_dict(u) for u in page], "total": total, "counts": counts}
    )


def create_user(request):
    data = json_body(request)
    institution = request.user.institution
    errors = []

    name = v.clean_name(data, errors)
    email = v.clean_email(data, errors)
    role = data.get("role")
    if role not in ROLES:
        errors.append({"field": "role", "message": "Choose a role: admin, educator or student"})
    password = v.clean_new_password(data.get("password"), errors)

    cohort = None
    if role == "student":
        cohort = find_cohort(institution, data.get("cohortId"))
        if cohort is None:
            errors.append({"field": "cohortId", "message": "Choose a cohort for this student"})

    require_change = data.get("requirePasswordChange", True)
    if not isinstance(require_change, bool):
        errors.append(
            {"field": "requirePasswordChange", "message": "requirePasswordChange must be true or false"}
        )
    v.raise_if(errors)

    duplicate = [{"field": "email", "message": "An account with this email already exists"}]
    if User.objects.filter(email=email).exists():
        return error(duplicate[0]["message"], 400, errors=duplicate)

    user = User(
        institution=institution,
        name=name,
        email=email,
        role=role,
        must_change_password=require_change,
    )
    user.place(cohort)
    user.set_password(password)
    try:
        user.save()
    except IntegrityError:  # lost a race with another request for the same email
        return error(duplicate[0]["message"], 400, errors=duplicate)
    where = f" in {cohort.label}" if cohort else ""
    AuditLog.record(
        institution,
        request.user,
        "user.created",
        f"Added {user.name} as {ROLE_LABELS[role].lower()}{where}",
        userId=str(user.pk),
    )
    return JsonResponse({"success": True, "user": member_dict(user)}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin")
@api_view
def users(request):
    return create_user(request) if request.method == "POST" else list_users(request)


@require_http_methods(["PATCH"])
@jwt_required
@role_required("admin")
@api_view
def user_detail(request, user_id):
    """Move a student to another cohort (and so its section, department and batch)."""
    institution = request.user.institution
    target = find_member(institution, user_id)
    if target is None:
        return error("User not found", 404)
    if target.role != "student":
        raise BadRequest("Only students belong to a cohort")
    cohort = find_cohort(institution, json_body(request).get("cohortId"))
    if cohort is None:
        message = "Choose a cohort for this student"
        raise BadRequest(message, [{"field": "cohortId", "message": message}])
    if cohort.pk != target.cohort_id:
        before = target.placement()
        target.place(cohort)
        target.save(update_fields=[*User.PLACEMENT_FIELDS, "updated_at"])
        AuditLog.record(
            institution,
            request.user,
            "user.moved",
            f"Moved {target.name} to {cohort.label}",
            userId=str(target.pk),
            fromLabel=before["label"] if before else None,
        )
    return JsonResponse({"success": True, "user": member_dict(target)})


# --------------------------------------------------------------------------- #
# Academic structure: Batch -> Department -> Section -> Cohort                 #
# --------------------------------------------------------------------------- #


def create_group(request):
    if request.user.role != "admin":
        return error("Only admins can change the academic structure", 403)
    institution = request.user.institution
    data = json_body(request)
    level = data.get("level")
    if level not in LEVELS:
        raise BadRequest("Choose a level: batch, department, section or cohort")
    label = LEVEL_LABELS[level]

    parent = None
    parent_level = structure.PARENT_LEVEL.get(level)
    if parent_level:
        parent = structure.find_node(institution, parent_level, data.get("parentId"))
        if parent is None:
            message = f"Choose the {LEVEL_LABELS[parent_level].lower()} this {label.lower()} belongs to"
            raise BadRequest(message, [{"field": "parentId", "message": message}])
    name = structure.clean_name(data.get("name"), level)

    model = MODELS[level]
    where = f" in {parent.label}" if parent else ""
    taken = f'A {label.lower()} named "{name}" already exists{where}'
    siblings = model.objects.filter(**structure.sibling_filter(level, parent, institution))
    if siblings.filter(name_key=model.key_for(name)).exists():
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    try:
        node = model.objects.create(
            institution=institution, name=name, **({parent_level: parent} if parent else {})
        )
    except IntegrityError:
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    AuditLog.record(
        institution, request.user, f"{level}.created", f"Created the {label.lower()} {node.label}"
    )
    return JsonResponse({"success": True, "node": structure.node_summary(node, {})}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@role_required("admin", "educator")
@api_view
def academic_structure(request):
    """GET: the whole tree with stats. POST {level, name, parentId}: add a group."""
    if request.method == "POST":
        return create_group(request)
    institution = request.user.institution
    return JsonResponse(
        {
            "batches": structure.tree(institution, stats.group_stats(institution)),
            "counts": structure.counts(institution),
        }
    )


def rename_group(request, node):
    institution = request.user.institution
    level, label = node.LEVEL, LEVEL_LABELS[node.LEVEL]
    name = structure.clean_name(json_body(request).get("name"), level)
    if name == node.name:
        return
    model = MODELS[level]
    taken = f'A {label.lower()} named "{name}" already exists here'
    siblings = model.objects.filter(**structure.sibling_filter(level, node.parent, institution)).exclude(pk=node.pk)
    if siblings.filter(name_key=model.key_for(name)).exists():
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    before = node.label
    node.name = name
    try:
        node.save(update_fields=["name"])
    except IntegrityError:
        raise BadRequest(taken, [{"field": "name", "message": taken}])
    AuditLog.record(
        institution, request.user, f"{level}.renamed", f"Renamed the {label.lower()} {before} to {node.name}"
    )


def delete_group(request, node):
    level, label = node.LEVEL, LEVEL_LABELS[node.LEVEL].lower()
    children = structure.CHILDREN.get(level)
    if children and getattr(node, children).exists():
        child = LEVEL_LABELS[structure.CHILD_LEVEL[level]].lower()
        return error(f"Delete this {label}'s {child}s first", 400)
    if User.objects.filter(**{level: node}).exists():
        return error(f"Move or remove this {label}'s students before deleting it", 400)
    if node.assessments.exists():
        return error(f"This {label} has tests assigned to it, so it can't be deleted", 400)
    if node.posts.exists():
        return error(f"This {label} has notes or messages posted to it, so it can't be deleted", 400)
    name = node.label
    node.delete()
    AuditLog.record(request.user.institution, request.user, f"{level}.deleted", f"Deleted the {label} {name}")
    return HttpResponse(status=204)


@require_http_methods(["GET", "PATCH", "DELETE"])
@jwt_required
@role_required("admin", "educator")
@api_view
def group_detail(request, level, node_id):
    institution = request.user.institution
    node = structure.find_node(institution, level, node_id)
    if node is None:
        return error(f"{LEVEL_LABELS.get(level, 'Group')} not found", 404)

    if request.method != "GET" and request.user.role != "admin":
        return error("Only admins can change the academic structure", 403)
    if request.method == "DELETE":
        return delete_group(request, node)
    if request.method == "PATCH":
        rename_group(request, node)

    group_stats = stats.group_stats(institution)
    lineage = node.lineage()
    entry = structure.node_summary(node, group_stats, lineage)
    children = structure.CHILDREN.get(level)
    if children:
        entry["children"] = [
            structure.node_summary(child, group_stats, [*lineage, child]) for child in getattr(node, children).all()
        ]
    return JsonResponse({"node": entry})


# --------------------------------------------------------------------------- #
# Dashboard                                                                    #
# --------------------------------------------------------------------------- #


@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def overview(request):
    institution = request.user.institution
    members = User.objects.filter(institution=institution)
    recent = list(
        PracticeAttempt.objects.filter(
            institution=institution, created_at__gte=stats.since(14)
        ).values_list("created_at", flat=True)
    )
    week_ago = stats.since(7)
    last_week = sum(ts >= week_ago for ts in recent)
    month_scores = PracticeAttempt.objects.filter(
        institution=institution, created_at__gte=stats.since(30)
    ).values_list("score", flat=True)
    group_stats = stats.group_stats(institution)
    departments = sorted(
        (
            structure.node_summary(d, group_stats, [d.batch, d])
            for d in MODELS["department"].objects.filter(institution=institution).select_related("batch")
        ),
        key=lambda d: (-d["studentCount"], d["label"].casefold()),
    )

    return JsonResponse(
        {
            "counts": {
                "students": members.filter(role="student").count(),
                "educators": members.filter(role="educator").count(),
                "admins": members.filter(role="admin").count(),
                **structure.counts(institution),
            },
            "activatedStudents": members.filter(role="student", last_login__isnull=False).count(),
            "practice": {
                "last7Days": last_week,
                "previous7Days": len(recent) - last_week,
                "averageScore": stats.average(month_scores),
                "daily": stats.daily_counts(recent, 14),
            },
            "departments": [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "label": d["label"],
                    "students": d["studentCount"],
                    "activated": d["activated"],
                    "averageScore": d["averageScore"],
                }
                for d in departments[:6]
            ],
        }
    )


@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def activity(request):
    limit = parse_int(request.GET.get("limit"), 20, low=1, high=100)
    logs = (
        AuditLog.objects.filter(institution=request.user.institution)
        .select_related("actor")
        .order_by("-created_at")[:limit]
    )
    return JsonResponse({"activity": [log.to_dict() for log in logs]})


# --------------------------------------------------------------------------- #
# Password reset                                                               #
# --------------------------------------------------------------------------- #


@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@api_view
def reset_password(request, user_id):
    institution = request.user.institution
    target = find_member(institution, user_id)
    if target is None:
        return error("User not found", 404)
    if target.pk == request.user.pk:
        raise BadRequest("Change your own password in Settings")

    password = json_body(request).get("password") or None
    if password is None:
        password = generate_password()
    else:
        errors = []
        v.clean_new_password(password, errors)
        v.raise_if(errors)

    target.set_password(password)
    target.must_change_password = True
    target.token_version += 1  # sign them out everywhere
    target.save(update_fields=["password", "must_change_password", "token_version", "updated_at"])
    clear_attempts(throttle_key("login", target.email))
    AuditLog.record(
        institution, request.user, "user.password_reset", f"Reset the password for {target.name}"
    )
    return JsonResponse({"success": True, "user": member_dict(target), "password": password})


# --------------------------------------------------------------------------- #
# CSV import                                                                   #
# --------------------------------------------------------------------------- #

IMPORT_COLUMNS = ("name", "email", "role", "password", *LEVELS)
REQUIRED_COLUMNS = ("name", "email", "role")


def _read_csv(upload):
    """[(line number, {column: value})] for every non-blank data row."""
    return read_csv(
        upload,
        columns=IMPORT_COLUMNS,
        required=REQUIRED_COLUMNS,
        example="name,email,role,password,batch,department,section,cohort",
        noun="people",
        max_rows=MAX_IMPORT_ROWS,
        max_bytes=MAX_IMPORT_BYTES,
    )


def _existing_groups(institution):
    """{level: {path of name keys: node}} for every group of the institution."""
    groups = {level: {} for level in LEVELS}
    for level in LEVELS:
        for node in MODELS[level].objects.filter(institution=institution).select_related(*ANCESTORS[level]):
            groups[level][tuple(n.name_key for n in node.lineage())] = node
    return groups


IMPORT_MODES = ("add", "update")


def _placement_path(user):
    """The user's (batch, department, section, cohort) name keys, or None."""
    if not user.cohort_id:
        return None
    return tuple(getattr(user, level).name_key for level in LEVELS)


def _changes(user, name, role, path, names, password):
    """What an update row would change about `user`, in words."""
    changes = []
    if name != user.name:
        changes.append(f"Name: {user.name} → {name}")
    if role != user.role:
        changes.append(f"Role: {ROLE_LABELS[user.role]} → {ROLE_LABELS[role]}")
    current = _placement_path(user)
    if path != current:
        if current and path:
            # Name the first level that differs and show the path from there down.
            first = next(i for i, (a, b) in enumerate(zip(current, path)) if a != b)
            old_names = [getattr(user, level).name for level in LEVELS]
            changes.append(
                f"{LEVEL_LABELS[LEVELS[first]]}: {' · '.join(old_names[first:])} → {' · '.join(names[first:])}"
            )
        else:
            before = user.placement()["label"] if current else "none"
            after = " · ".join(names) if path else "none"
            changes.append(f"Placement: {before} → {after}")
    if password:
        changes.append("New password (they'll be signed out)")
    return changes


def _check_rows(institution, records, create_groups, mode="add", actor=None):
    """Validate every row. Returns (rows, existing groups, groups to create, unknown
    groups); the last two map (level, path of name keys) -> label.

    mode "add": every email must be new. mode "update": every email must be a user
    of this institution, matched case-insensitively; rows list their `changes`."""
    groups = _existing_groups(institution)
    emails = [e for e in (values.get("email", "").lower() for _, values in records) if e]
    if mode == "add":
        taken = set(User.objects.filter(email__in=emails).values_list("email", flat=True))
    else:
        members = {
            u.email: u
            for u in User.objects.filter(institution=institution, email__in=emails).select_related(
                *User.PLACEMENT_FIELDS
            )
        }
    first_line = {}
    to_create, unknown = {}, {}
    rows = []

    for line, values in records:
        errors = []
        name = " ".join(values.get("name", "").split())
        email = values.get("email", "").lower()
        role = values.get("role", "").lower()
        password = values.get("password", "")
        names = [Cohort.clean_name(values.get(level, "")) if role == "student" else "" for level in LEVELS]
        member = None

        if not 2 <= len(name) <= 50:
            errors.append("Name is missing" if not name else "Name must be 2-50 characters")
        try:
            validate_email(email)
        except ValidationError:
            errors.append("Email is missing" if not email else "Email isn't valid")
        else:
            if email in first_line:
                errors.append(f"Same email as row {first_line[email]}")
            elif mode == "add" and email in taken:
                errors.append("An account with this email already exists")
            elif mode == "update" and email not in members:
                # Also for other institutions' accounts: never reveal they exist.
                errors.append("No user with this email in your institution")
            else:
                first_line[email] = line
                member = members[email] if mode == "update" else None
        if role not in ROLE_LABELS:
            errors.append("Role must be admin, educator or student")
        elif member and actor and member.pk == actor.pk and role != member.role:
            errors.append("You can't change your own role")
        if password:
            problems = []
            v.clean_new_password(password, problems)
            errors += [p["message"] for p in problems]
        if role == "student":
            blank = [LEVEL_LABELS[level].lower() for level, n in zip(LEVELS, names) if not n]
            long = [LEVEL_LABELS[level] for level, n in zip(LEVELS, names) if len(n) > structure.MAX_NAME]
            if blank:
                errors.append(f"Students need a {', '.join(blank)}")
            elif long:
                errors.append(f"{long[0]} names can be at most {structure.MAX_NAME} characters")
            else:
                keys = tuple(Cohort.key_for(n) for n in names)
                for depth, level in enumerate(LEVELS, start=1):
                    path = keys[:depth]
                    if path in groups[level]:
                        continue
                    label = " · ".join(names[:depth])
                    if create_groups:
                        to_create.setdefault((level, path), label)
                    else:
                        unknown.setdefault((level, path), label)
                        errors.append(f'{LEVEL_LABELS[level]} "{label}" doesn\'t exist')
                        break  # its children can't exist either

        path = tuple(Cohort.key_for(n) for n in names) if role == "student" else None
        row = {
            "line": line,
            "name": name,
            "email": email,
            "role": role if role in ROLE_LABELS else values.get("role", ""),
            "placement": " · ".join(n for n in names if n),
            "passwordProvided": bool(password),
            "errors": errors,
            "_password": password,
            "_path": path,
            "_names": names,
            "_user": member,
        }
        if mode == "update":
            row["changes"] = (
                _changes(member, name, role, path, names, password) if member and not errors else []
            )
        rows.append(row)
    return rows, groups, to_create, unknown


def _group_list(found):
    """[{level, label}] sorted from the top of the tree down."""
    return [
        {"level": level, "label": label}
        for (level, _), label in sorted(found.items(), key=lambda item: (LEVELS.index(item[0][0]), item[1].casefold()))
    ]


def _public(row):
    return {k: val for k, val in row.items() if not k.startswith("_")}


def _create_groups(institution, rows, groups, to_create):
    """Create the missing groups `rows` need, parents before children. Returns
    {(level, path): label} of the groups created."""
    needed = {r["_path"][:depth] for r in rows if r["_path"] for depth in range(1, len(LEVELS) + 1)}
    # The first row's spelling wins, matching the labels shown in the preview.
    names = {}
    for r in rows:
        for depth in range(1, len(LEVELS) + 1) if r["_path"] else ():
            names.setdefault(r["_path"][:depth], r["_names"][depth - 1])
    created = {}
    for level, path in sorted(to_create, key=lambda key: LEVELS.index(key[0])):
        if path not in needed:
            continue
        parent_level = structure.PARENT_LEVEL.get(level)
        parent = {parent_level: groups[parent_level][path[:-1]]} if parent_level else {}
        try:
            groups[level][path] = MODELS[level].objects.create(institution=institution, name=names[path], **parent)
            created[(level, path)] = groups[level][path].label
        except IntegrityError:  # created concurrently
            groups[level][path] = MODELS[level].objects.get(institution=institution, name_key=path[-1], **parent)
    return created


def _add_users(request, rows, valid, groups, created_groups):
    institution = request.user.institution
    passwords = [r["_password"] or generate_password() for r in valid]
    hashes = hash_many(passwords)
    created, credentials = 0, []
    for row, password, hashed in zip(valid, passwords, hashes):
        user = User(
            institution=institution,
            name=row["name"],
            email=row["email"],
            role=row["role"],
            password=hashed,
            must_change_password=True,
        )
        user.place(groups["cohort"][row["_path"]] if row["_path"] else None)
        try:
            user.save()
        except IntegrityError:  # email claimed since validation
            row["errors"].append("An account with this email already exists")
            continue
        created += 1
        if not row["_password"]:
            credentials.append({"name": user.name, "email": user.email, "password": password})

    if created:
        made = sorted(created_groups.values(), key=str.casefold)
        extra = f" and created {', '.join(made)}" if made else ""
        AuditLog.record(
            institution,
            request.user,
            "users.imported",
            f"Imported {created} user{'s' if created != 1 else ''} from a CSV file{extra}",
            created=created,
            skipped=len(rows) - created,
        )
    return JsonResponse(
        {
            "mode": "add",
            "created": created,
            "skipped": len(rows) - created,
            "credentials": credentials,
            "groupsCreated": _group_list(created_groups),
            "rows": [_public(r) for r in rows],
        },
        status=201,
    )


def _update_users(request, rows, valid, groups, created_groups):
    institution = request.user.institution
    changing = [r for r in valid if r["changes"]]
    with_password = [r for r in changing if r["_password"]]
    hashes = dict(zip((id(r) for r in with_password), hash_many([r["_password"] for r in with_password])))
    for row in changing:
        user = row["_user"]
        sign_out = row["role"] != user.role or bool(row["_password"])
        user.name = row["name"]
        user.role = row["role"]
        user.place(groups["cohort"][row["_path"]] if row["_path"] else None)
        fields = ["name", "role", *User.PLACEMENT_FIELDS, "updated_at"]
        if row["_password"]:
            user.password = hashes[id(row)]
            user.must_change_password = True
            fields += ["password", "must_change_password"]
        if sign_out:  # their tokens describe the old account
            user.token_version += 1
            fields.append("token_version")
        user.save(update_fields=fields)
        if row["_password"]:
            clear_attempts(throttle_key("login", user.email))

    if changing:
        made = sorted(created_groups.values(), key=str.casefold)
        extra = f" and created {', '.join(made)}" if made else ""
        AuditLog.record(
            institution,
            request.user,
            "users.updated",
            f"Updated {len(changing)} user{'s' if len(changing) != 1 else ''} from a CSV file{extra}",
            updated=len(changing),
            unchanged=len(valid) - len(changing),
            skipped=len(rows) - len(valid),
        )
    return JsonResponse(
        {
            "mode": "update",
            "updated": len(changing),
            "unchanged": len(valid) - len(changing),
            "skipped": len(rows) - len(valid),
            "groupsCreated": _group_list(created_groups),
            "rows": [_public(r) for r in rows],
        },
        status=200,
    )


@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@api_view
def import_users(request):
    """Multipart `file` (CSV). `mode` "add" (default) creates new people;
    "update" changes existing ones, matched by email. commit=false checks
    every row; commit=true applies the valid ones."""
    institution = request.user.institution
    commit = request.POST.get("commit") == "true"
    create_groups = request.POST.get("createGroups") == "true"
    mode = request.POST.get("mode", "add")
    if mode not in IMPORT_MODES:
        raise BadRequest("mode must be add or update")
    records = _read_csv(request.FILES.get("file"))
    rows, groups, to_create, unknown = _check_rows(institution, records, create_groups, mode, request.user)
    valid = [r for r in rows if not r["errors"]]

    summary = {"total": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid)}
    if mode == "update":
        summary["changing"] = sum(1 for r in valid if r["changes"])
    if not commit:
        return JsonResponse(
            {
                "mode": mode,
                "rows": [_public(r) for r in rows],
                "summary": summary,
                "missingGroups": _group_list(unknown),
                "newGroups": _group_list(to_create),
            }
        )
    if not valid:
        raise BadRequest("None of the rows can be imported. Fix the problems and try again.")
    if mode == "update" and not summary["changing"]:
        raise BadRequest("Nothing to update: every valid row matches what's already saved.")

    created_groups = _create_groups(institution, valid, groups, to_create)
    handler = _update_users if mode == "update" else _add_users
    return handler(request, rows, valid, groups, created_groups)


@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
@api_view
def export_users(request):
    """The institution's users as CSV, in the import's columns (passwords are
    never exported), honouring the list filters: role, batch/department/
    section/cohort and q. Edit it and import it again with mode "update"."""
    institution = request.user.institution
    members = User.objects.filter(institution=institution)
    role = request.GET.get("role", "").strip()
    if role:
        if role not in ROLES:
            raise BadRequest("Unknown role filter")
        members = members.filter(role=role)
    members = structure.filter_by_groups(members, institution, request.GET)
    query = clean_query(request.GET.get("q"), MAX_SEARCH_LEN)
    if query:
        members = members.filter(Q(name__icontains=query) | Q(email__icontains=query))

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(IMPORT_COLUMNS)
    for user in members.select_related(*User.PLACEMENT_FIELDS).order_by("role", "name"):
        placement = [getattr(user, level).name if getattr(user, f"{level}_id") else "" for level in LEVELS]
        writer.writerow([safe_cell(c) for c in (user.name, user.email, user.role, "", *placement)])

    # A BOM so Excel reads names with accents correctly; the importer accepts it.
    response = HttpResponse("\ufeff" + out.getvalue(), content_type="text/csv; charset=utf-8")
    stamp = timezone.localdate().isoformat()
    response["Content-Disposition"] = f'attachment; filename="users-{institution.slug}-{stamp}.csv"'
    response["Cache-Control"] = "private, no-store"
    return response


# --------------------------------------------------------------------------- #
# Institution profile and branding                                             #
# --------------------------------------------------------------------------- #


@require_http_methods(["GET", "PATCH"])
@jwt_required
@api_view
def profile(request):
    institution = request.user.institution
    if request.method == "GET":
        return JsonResponse({"institution": institution.to_dict()})
    if request.user.role != "admin":
        return error("Only admins can change institution details", 403)

    data = json_body(request)
    errors, changed = [], []

    if "name" in data:
        name = " ".join(data["name"].split()) if isinstance(data["name"], str) else ""
        problem = institution_rules.name_error(name, exclude=institution)
        if problem:
            errors.append({"field": "name", "message": problem})
        elif name != institution.name:
            institution.name = name
            changed.append("name")
    if "academicYear" in data:
        year = data["academicYear"].strip() if isinstance(data["academicYear"], str) else ""
        problem = institution_rules.academic_year_error(year)
        if problem:
            errors.append({"field": "academicYear", "message": problem})
        elif year != institution.academic_year:
            institution.academic_year = year
            changed.append("academic_year")
    if "website" in data:
        website = institution_rules.clean_website(data["website"]) if isinstance(data["website"], str) else None
        problem = "Enter a valid website URL." if website is None else (
            institution_rules.website_error(website) if website else None
        )
        if problem:
            errors.append({"field": "website", "message": problem})
        elif website != institution.website:
            institution.website = website
            changed.append("website")
    v.raise_if(errors)

    if changed:
        institution.save(update_fields=changed + ["updated_at"])
        summary = (
            f"Renamed the institution to {institution.name}"
            if changed == ["name"]
            else "Updated the institution details"
        )
        AuditLog.record(institution, request.user, "institution.updated", summary, fields=changed)
    return JsonResponse({"success": True, "institution": institution.to_dict()})


@require_http_methods(["POST", "DELETE"])
@jwt_required
@role_required("admin")
@api_view
def institution_logo(request):
    institution = request.user.institution
    if request.method == "DELETE":
        institution.logo, institution.logo_version = None, ""
        action, summary = "institution.logo_removed", "Removed the institution logo"
    else:
        institution.logo, institution.logo_version = process_logo(request.FILES.get("logo"))
        action, summary = "institution.logo_updated", "Updated the institution logo"
    institution.save(update_fields=["logo", "logo_version", "updated_at"])
    AuditLog.record(institution, request.user, action, summary)
    return JsonResponse({"success": True, "institution": institution.to_dict()})


@require_http_methods(["GET"])
def logo(request, institution_id):
    """Public: the logo appears in <img> tags, which can't send a Bearer token.
    Logos aren't sensitive, and institution ids aren't enumerable listings."""
    try:
        institution = (
            Institution.objects.only("logo", "logo_version", "is_active").filter(pk=institution_id).first()
        )
    except ValidationError:
        institution = None
    if institution is None or not institution.is_active or not institution.logo:
        return HttpResponse(status=404)

    response = HttpResponse(bytes(institution.logo), content_type="image/png")
    versioned = request.GET.get("v") == institution.logo_version
    response["Cache-Control"] = "public, max-age=31536000, immutable" if versioned else "public, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'"
    response["Cross-Origin-Resource-Policy"] = "cross-origin"  # shown by the client on another origin
    return response


@require_http_methods(["GET"])
def branding(request, slug):
    """Public: name, logo and colours for an institution's sign-in page (/login?school=<slug>)."""
    institution = (
        Institution.objects.defer("logo").filter(slug=slug, is_active=True).first()
    )
    if institution is None:
        return error("Institution not found", 404)
    return JsonResponse(
        {
            "name": institution.name,
            "type": institution.type,
            "slug": institution.slug,
            "logoUrl": institution.logo_url,
            "theme": theme_dict(institution),
        }
    )
