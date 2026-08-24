"""Deterministic submission-key / branch-name derivation for user-submitted automations."""
import hashlib
import re

BRANCH_PREFIX = "user-automation"
SLUG_MAX_LEN = 50
HASH_LEN = 12


def slugify(automation_name: str) -> str:
    """Returns automation_name as a branch-safe slug, capped at SLUG_MAX_LEN chars."""
    slug = automation_name.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:SLUG_MAX_LEN]


def submission_hash(thread_id, user_id, automation_name: str) -> str:
    """Returns the first HASH_LEN hex chars of sha256 over (thread_id, user_id, normalized name)."""
    normalized_name = automation_name.strip().lower()
    digest = hashlib.sha256(f"{thread_id}:{user_id}:{normalized_name}".encode()).hexdigest()
    return digest[:HASH_LEN]


def branch_name(thread_id, user_id, automation_name: str, branch_prefix: str = BRANCH_PREFIX) -> str:
    """Returns the deterministic submission branch name: `<branch_prefix>/<slug>-<hash>`."""
    slug = slugify(automation_name)
    digest = submission_hash(thread_id, user_id, automation_name)
    return f"{branch_prefix}/{slug}-{digest}"
