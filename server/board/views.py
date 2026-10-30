"""Notes and messages.

Admins and educators post to a batch, department, section or cohort; every
student beneath that group can read the post and download its attachments.
Educators manage their own posts, admins manage every post. Everything is
scoped to the caller's institution.
"""
import os
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.auth import jwt_required, role_required
from accounts.models import User
from config.http import BadRequest, api_view, clean_query, error, json_body
from institutions import structure
from institutions.models import LEVELS, AuditLog

from .models import Attachment, Comment, Post, PostRead, Reaction

STAFF = ("admin", "educator")
KINDS = [kind for kind, _ in Post.KIND_CHOICES]
KIND_LABELS = dict(Post.KIND_CHOICES)
MAX_TITLE = 200
MAX_BODY = 10_000
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILE_NAME = 200
MAX_COMMENT = 2000
COMMENTS_PAGE = 50
DEFAULT_PAGE = 20
MAX_PAGE = 100
# The stored type comes from the extension, never from the browser, and files
# are always served as downloads (see download_attachment).
FILE_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".md": "text/markdown",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _int(raw, default, low, high):
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        return default


def _posts():
    return Post.objects.select_related(*Post.AUDIENCE_FIELDS, "author")


def _find_post(request, post_id):
    """The post with that id if the caller may see it, else None."""
    user = request.user
    posts = Post.for_student(user) if user.role == "student" else Post.objects.filter(institution=user.institution)
    try:
        return posts.select_related(*Post.AUDIENCE_FIELDS, "author").filter(pk=post_id).first()
    except ValidationError:  # not a valid ObjectId
        return None


def _can_edit(user, post):
    return user.role == "admin" or (user.role == "educator" and post.author_id == user.pk)


def _attachments(post_ids):
    """{post id: [attachment dicts]} without loading file contents."""
    by_post = {}
    for attachment in Attachment.objects.filter(post_id__in=list(post_ids)).defer("data"):
        by_post.setdefault(attachment.post_id, []).append(attachment.to_dict())
    return by_post


def _readers(institution, posts):
    """{post id: number of students currently in its audience who have opened it}."""
    if not posts:
        return {}
    placement = {
        pk: dict(zip(LEVELS, ids))
        for pk, *ids in User.objects.filter(institution=institution, role="student", cohort__isnull=False).values_list(
            "pk", *(f"{level}_id" for level in LEVELS)
        )
    }
    targets = {post.pk: post.audience_key() for post in posts}
    counts = dict.fromkeys(targets, 0)
    for post_id, user_id in PostRead.objects.filter(post_id__in=list(targets)).values_list("post_id", "user_id"):
        level, group_id = targets[post_id]
        if placement.get(user_id, {}).get(level) == group_id:
            counts[post_id] += 1
    return counts


def _social(viewer, post_ids):
    """{post id: {"reactions": [{kind, count, mine}], "commentCount": n}} in two queries."""
    post_ids = list(post_ids)
    social = {pk: {"reactions": {}, "mine": set(), "commentCount": 0} for pk in post_ids}
    for post_id, user_id, kind in Reaction.objects.filter(post_id__in=post_ids).values_list("post_id", "user_id", "kind"):
        entry = social[post_id]
        entry["reactions"][kind] = entry["reactions"].get(kind, 0) + 1
        if user_id == viewer.pk:
            entry["mine"].add(kind)
    for post_id in Comment.objects.filter(post_id__in=post_ids).values_list("post_id", flat=True):
        social[post_id]["commentCount"] += 1
    return {
        pk: {
            # In the fixed order of Reaction.KINDS, so chips never jump around.
            "reactions": [
                {"kind": kind, "count": e["reactions"][kind], "mine": kind in e["mine"]}
                for kind in Reaction.KINDS
                if kind in e["reactions"]
            ],
            "commentCount": e["commentCount"],
        }
        for pk, e in social.items()
    }


def post_dict(post, viewer, attachments, *, social=None, read=None, readers=None, audience_size=None):
    data = {
        "id": str(post.pk),
        "kind": post.kind,
        "title": post.title,
        "body": post.body,
        "pinned": post.pinned,
        "audience": post.audience_dict(),
        "author": {"id": str(post.author_id), "name": post.author.name, "role": post.author.role}
        if post.author_id
        else None,
        "attachments": attachments,
        "createdAt": post.created_at,
        "editedAt": post.edited_at,
        # Posts saved before comments existed have no value yet: comments are on.
        "commentsEnabled": post.comments_enabled is not False,
        **(social or {"reactions": [], "commentCount": 0}),
    }
    if viewer.role == "student":
        data["read"] = read
    else:
        data["canEdit"] = _can_edit(viewer, post)
        data["readers"] = readers or 0
        data["audienceSize"] = audience_size or 0
    return data


def _serialise(request, posts):
    viewer = request.user
    attachments = _attachments(p.pk for p in posts)
    social = _social(viewer, (p.pk for p in posts))
    if viewer.role == "student":
        read = set(
            PostRead.objects.filter(user=viewer, post_id__in=[p.pk for p in posts]).values_list("post_id", flat=True)
        )
        return [
            post_dict(p, viewer, attachments.get(p.pk, []), social=social[p.pk], read=p.pk in read) for p in posts
        ]
    sizes = structure.student_counts(viewer.institution)
    readers = _readers(viewer.institution, posts)
    return [
        post_dict(
            p,
            viewer,
            attachments.get(p.pk, []),
            social=social[p.pk],
            readers=readers.get(p.pk),
            audience_size=sizes.get(p.audience_key(), 0),
        )
        for p in posts
    ]


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #


def _clean_text(value, field, label, limit, errors, *, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        errors.append({"field": field, "message": f"{label} must be text"})
        return ""
    value = " ".join(value.split()) if field == "title" else value.strip()
    if required and not value:
        errors.append({"field": field, "message": f"Add a {label.lower()}"})
    elif len(value) > limit:
        errors.append({"field": field, "message": f"{label} can be at most {limit:,} characters"})
    return value


def _clean_audience(institution, level, node_id, errors):
    node = structure.find_node(institution, level, node_id)
    if node is None:
        errors.append({"field": "audience", "message": "Choose who can see this"})
    return node


def _clean_files(uploads, already=0):
    """[(name, content type, bytes)] or raise BadRequest."""
    if already + len(uploads) > MAX_FILES:
        raise BadRequest(
            f"Attach at most {MAX_FILES} files to a post",
            [{"field": "files", "message": f"Attach at most {MAX_FILES} files to a post"}],
        )
    files = []
    for upload in uploads:
        name = os.path.basename((upload.name or "").replace("\\", "/")).strip() or "file"
        stem, ext = os.path.splitext(name)
        content_type = FILE_TYPES.get(ext.lower())
        # Shorten long names without cutting off the extension.
        name = stem[: MAX_FILE_NAME - len(ext)] + ext if content_type else name[:MAX_FILE_NAME]
        if content_type is None:
            message = f'"{name}" isn\'t a supported file. Share PDFs, images, text or Office documents.'
            raise BadRequest(message, [{"field": "files", "message": message}])
        if upload.size > MAX_FILE_BYTES:
            message = f'"{name}" is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB'
            raise BadRequest(message, [{"field": "files", "message": message}])
        if upload.size == 0:
            message = f'"{name}" is empty'
            raise BadRequest(message, [{"field": "files", "message": message}])
        files.append((name, content_type, upload.read()))
    return files


def _save_files(post, files):
    for name, content_type, data in files:
        Attachment.objects.create(post=post, name=name, content_type=content_type, size=len(data), data=data)


# --------------------------------------------------------------------------- #
# Posts                                                                        #
# --------------------------------------------------------------------------- #


def list_posts(request):
    user = request.user
    if user.role == "student":
        posts = Post.for_student(user)
    else:
        posts = structure.filter_by_groups(Post.objects.filter(institution=user.institution), user.institution, request.GET)
        if request.GET.get("mine") == "true":
            posts = posts.filter(author=user)

    kind = request.GET.get("kind", "").strip()
    if kind:
        if kind not in KINDS:
            raise BadRequest("Unknown kind")
        posts = posts.filter(kind=kind)
    query = clean_query(request.GET.get("q"))
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(body__icontains=query))

    total = posts.count()
    offset = _int(request.GET.get("offset"), 0, 0, 1_000_000)
    limit = _int(request.GET.get("limit"), DEFAULT_PAGE, 1, MAX_PAGE)
    page = list(
        posts.select_related(*Post.AUDIENCE_FIELDS, "author").order_by("-pinned", "-created_at")[
            offset : offset + limit
        ]
    )
    return JsonResponse({"posts": _serialise(request, page), "total": total})


def create_post(request):
    if request.user.role not in STAFF:
        return error("Only admins and educators can post", 403)
    institution = request.user.institution
    data = request.POST
    errors = []
    kind = data.get("kind", "message")
    if kind not in KINDS:
        errors.append({"field": "kind", "message": "Choose message or note"})
    title = _clean_text(data.get("title"), "title", "Title", MAX_TITLE, errors, required=True)
    body = _clean_text(data.get("body"), "body", "Text", MAX_BODY, errors)
    audience = _clean_audience(institution, data.get("audienceLevel"), data.get("audienceId"), errors)
    if errors:
        raise BadRequest(errors[0]["message"], errors)
    files = _clean_files(request.FILES.getlist("files"))
    if kind == "message" and not body and not files:
        message = "Write a message or attach a file"
        raise BadRequest(message, [{"field": "body", "message": message}])

    post = Post(
        institution=institution,
        author=request.user,
        kind=kind,
        title=title,
        body=body,
        pinned=data.get("pinned") == "true",
        comments_enabled=data.get("commentsEnabled") != "false",
    )
    post.set_audience(audience)
    post.save()
    _save_files(post, files)
    AuditLog.record(
        institution,
        request.user,
        "post.created",
        f"Posted the {KIND_LABELS[kind].lower()} {title} to {audience.label}",
        postId=str(post.pk),
    )
    return JsonResponse({"success": True, "post": _serialise(request, [post])[0]}, status=201)


@require_http_methods(["GET", "POST"])
@jwt_required
@api_view
def posts(request):
    """GET: the posts the caller can see. POST (multipart): staff share a post."""
    return create_post(request) if request.method == "POST" else list_posts(request)


def update_post(request, post):
    data = json_body(request)
    errors, changed = [], []
    if "title" in data:
        title = _clean_text(data["title"], "title", "Title", MAX_TITLE, errors, required=True)
        if title != post.title:
            post.title = title
            changed.append("title")
    if "body" in data:
        body = _clean_text(data["body"], "body", "Text", MAX_BODY, errors)
        if body != post.body:
            post.body = body
            changed.append("body")
    if "commentsEnabled" in data:
        if not isinstance(data["commentsEnabled"], bool):
            errors.append({"field": "commentsEnabled", "message": "commentsEnabled must be true or false"})
        elif data["commentsEnabled"] != post.comments_enabled:
            post.comments_enabled = data["commentsEnabled"]
            changed.append("comments_enabled")
    if "pinned" in data:
        if not isinstance(data["pinned"], bool):
            errors.append({"field": "pinned", "message": "pinned must be true or false"})
        elif data["pinned"] != post.pinned:
            post.pinned = data["pinned"]
            changed.append("pinned")
    if "audience" in data:
        audience = data["audience"] if isinstance(data["audience"], dict) else {}
        node = _clean_audience(request.user.institution, audience.get("level"), audience.get("id"), errors)
        if node is not None and (node.LEVEL, node.pk) != post.audience_key():
            post.set_audience(node)
            changed += list(Post.AUDIENCE_FIELDS)
    if errors:
        raise BadRequest(errors[0]["message"], errors)
    if changed:
        if {"title", "body"} & set(changed):
            post.edited_at = timezone.now()
            changed.append("edited_at")
        post.save(update_fields=changed)


@require_http_methods(["GET", "PATCH", "DELETE"])
@jwt_required
@api_view
def post_detail(request, post_id):
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)
    if request.method != "GET":
        if not _can_edit(request.user, post):
            return error("Only the author or an admin can change this post", 403)
        if request.method == "DELETE":
            title = post.title
            post.delete()
            AuditLog.record(request.user.institution, request.user, "post.deleted", f"Deleted the post {title}")
            return HttpResponse(status=204)
        update_post(request, post)
    return JsonResponse({"post": _serialise(request, [post])[0]})


def _mark_read(post, user):
    if user.role != "student":
        return
    try:
        PostRead.objects.get_or_create(post=post, user=user)
    except IntegrityError:  # marked read by a concurrent request
        pass


@require_http_methods(["POST"])
@jwt_required
@role_required("student")
def mark_read(request, post_id):
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)
    _mark_read(post, request.user)
    return JsonResponse({"read": True})


@require_http_methods(["GET"])
@jwt_required
def unread(request):
    """How many posts the student hasn't opened yet (0 for staff)."""
    user = request.user
    if user.role != "student":
        return JsonResponse({"unread": 0})
    visible = set(Post.for_student(user).values_list("pk", flat=True))
    read = set(PostRead.objects.filter(user=user, post_id__in=list(visible)).values_list("post_id", flat=True))
    return JsonResponse({"unread": len(visible - read)})


# --------------------------------------------------------------------------- #
# Attachments                                                                  #
# --------------------------------------------------------------------------- #


@require_http_methods(["POST"])
@jwt_required
@role_required(*STAFF)
@api_view
def add_attachments(request, post_id):
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)
    if not _can_edit(request.user, post):
        return error("Only the author or an admin can change this post", 403)
    uploads = request.FILES.getlist("files")
    if not uploads:
        raise BadRequest("Choose a file to attach", [{"field": "files", "message": "Choose a file to attach"}])
    _save_files(post, _clean_files(uploads, already=post.attachments.count()))
    post.edited_at = timezone.now()
    post.save(update_fields=["edited_at"])
    return JsonResponse({"post": _serialise(request, [post])[0]}, status=201)


@require_http_methods(["GET", "DELETE"])
@jwt_required
def attachment_detail(request, post_id, attachment_id):
    post = _find_post(request, post_id)
    if post is None:
        return error("File not found", 404)
    try:
        attachment = Attachment.objects.filter(post=post, pk=attachment_id).first()
    except ValidationError:
        attachment = None
    if attachment is None:
        return error("File not found", 404)

    if request.method == "DELETE":
        if not _can_edit(request.user, post):
            return error("Only the author or an admin can change this post", 403)
        attachment.delete()
        post.edited_at = timezone.now()
        post.save(update_fields=["edited_at"])
        return HttpResponse(status=204)

    response = HttpResponse(bytes(attachment.data), content_type=attachment.content_type)
    # Always a download, never rendered on our origin; the name is RFC 5987-encoded.
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(attachment.name)}"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Cache-Control"] = "private, no-store"
    return response


# --------------------------------------------------------------------------- #
# Comments and reactions                                                      #
# --------------------------------------------------------------------------- #
# Anyone who can see a post (students in its audience, every staff member) can
# comment on it and react to it. People delete their own comments; the post's
# author and admins can delete any comment on it, and turn comments off.


def _can_delete_comment(user, post, comment):
    return comment.author_id == user.pk or _can_edit(user, post)


def comment_dict(comment, viewer, post):
    return {
        "id": str(comment.pk),
        "body": comment.body,
        "author": {"id": str(comment.author_id), "name": comment.author.name, "role": comment.author.role},
        "createdAt": comment.created_at,
        "mine": comment.author_id == viewer.pk,
        "canDelete": _can_delete_comment(viewer, post, comment),
    }


@require_http_methods(["GET", "POST"])
@jwt_required
@api_view
def comments(request, post_id):
    """GET: the post's comments, oldest first (?offset=&limit=). POST {body}: add one."""
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)

    if request.method == "POST":
        if post.comments_enabled is False:
            return error("Comments are turned off for this post", 403)
        errors = []
        body = _clean_text(json_body(request).get("body"), "body", "Comment", MAX_COMMENT, errors, required=True)
        if errors:
            raise BadRequest(errors[0]["message"], errors)
        comment = Comment.objects.create(post=post, author=request.user, body=body)
        _mark_read(post, request.user)
        return JsonResponse({"comment": comment_dict(comment, request.user, post)}, status=201)

    found = Comment.objects.filter(post=post)
    total = found.count()
    offset = _int(request.GET.get("offset"), 0, 0, 1_000_000)
    limit = _int(request.GET.get("limit"), COMMENTS_PAGE, 1, MAX_PAGE)
    page = found.select_related("author").order_by("created_at", "pk")[offset : offset + limit]
    return JsonResponse({"comments": [comment_dict(c, request.user, post) for c in page], "total": total})


@require_http_methods(["DELETE"])
@jwt_required
def comment_detail(request, post_id, comment_id):
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)
    try:
        comment = Comment.objects.filter(post=post, pk=comment_id).first()
    except ValidationError:
        comment = None
    if comment is None:
        return error("Comment not found", 404)
    if not _can_delete_comment(request.user, post, comment):
        return error("You can only delete your own comments", 403)
    comment.delete()
    return HttpResponse(status=204)


@require_http_methods(["PUT", "DELETE"])
@jwt_required
def reaction(request, post_id, kind):
    """PUT adds the caller's reaction of this kind (once); DELETE removes it.
    Both return the post's reactions."""
    post = _find_post(request, post_id)
    if post is None:
        return error("Post not found", 404)
    if kind not in Reaction.KINDS:
        return error(f"Unknown reaction. Use one of: {', '.join(Reaction.KINDS)}", 400)
    if request.method == "PUT":
        try:
            Reaction.objects.get_or_create(post=post, user=request.user, kind=kind)
        except IntegrityError:  # added by a concurrent request
            pass
        _mark_read(post, request.user)
    else:
        Reaction.objects.filter(post=post, user=request.user, kind=kind).delete()
    return JsonResponse({"reactions": _social(request.user, [post.pk])[post.pk]["reactions"]})
