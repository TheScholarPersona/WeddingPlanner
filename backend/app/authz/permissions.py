"""Permissions and roles (see "Rollen und Berechtigungen").

Roles are sets of permissions defined in code, so they are versioned and tested.
Project-level permissions (tasks, budget, ...) are added with their modules.
"""

from enum import StrEnum

from app.organizations.models import OrgRole


class Perm(StrEnum):
    ORG_READ = "organization:read"
    ORG_UPDATE = "organization:update"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    INVITATIONS_MANAGE = "invitations:manage"
    AUDIT_READ = "audit:read"


ROLE_PERMS: dict[OrgRole, frozenset[Perm]] = {
    OrgRole.ORG_ADMIN: frozenset(Perm),
    OrgRole.MEMBER: frozenset({Perm.ORG_READ, Perm.MEMBERS_READ}),
    # Clients only need the organization's branding; everything else is project-scoped.
    OrgRole.CLIENT: frozenset({Perm.ORG_READ}),
}


def has_perm(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMS[OrgRole(role)]
    except ValueError:
        return False
