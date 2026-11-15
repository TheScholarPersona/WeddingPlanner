"""Permissions and roles (see "Rollen und Berechtigungen").

Roles are sets of permissions defined in code, so they are versioned and tested.
Organization roles grant `Perm`; project roles (per wedding) grant `ProjectPerm`.
"""

from enum import StrEnum

from app.organizations.models import OrgRole
from app.projects.models import ProjectRole


class Perm(StrEnum):
    ORG_READ = "organization:read"
    ORG_UPDATE = "organization:update"
    MEMBERS_READ = "members:read"
    MEMBERS_MANAGE = "members:manage"
    INVITATIONS_MANAGE = "invitations:manage"
    AUDIT_READ = "audit:read"
    DASHBOARD_READ = "dashboard:read"
    CLIENTS_READ = "clients:read"
    CLIENTS_WRITE = "clients:write"
    CLIENTS_DELETE = "clients:delete"
    VENDORS_READ = "vendors:read"
    VENDORS_WRITE = "vendors:write"
    PROJECTS_LIST = "projects:list"
    PROJECTS_CREATE = "projects:create"
    TEMPLATES_READ = "templates:read"
    TEMPLATES_MANAGE = "templates:manage"


_TEAM = frozenset(
    {
        Perm.ORG_READ,
        Perm.MEMBERS_READ,
        Perm.DASHBOARD_READ,
        Perm.CLIENTS_READ,
        Perm.CLIENTS_WRITE,
        Perm.VENDORS_READ,
        Perm.VENDORS_WRITE,
        Perm.PROJECTS_LIST,
        Perm.PROJECTS_CREATE,
        Perm.TEMPLATES_READ,
    }
)

ROLE_PERMS: dict[OrgRole, frozenset[Perm]] = {
    OrgRole.ORG_ADMIN: frozenset(Perm),
    OrgRole.MEMBER: _TEAM,
    # Clients only need the organization's branding; everything else is project-scoped.
    OrgRole.CLIENT: frozenset({Perm.ORG_READ}),
}


class ProjectPerm(StrEnum):
    READ = "project:read"
    UPDATE = "project:update"
    MANAGE_TEAM = "project:manage_team"
    ARCHIVE = "project:archive"
    DELETE = "project:delete"
    VENDORS_READ = "project_vendors:read"
    VENDORS_MANAGE = "project_vendors:manage"


# Org admins act as "admin" in every wedding: everything a lead may do, plus deleting.
ADMIN_PROJECT_ROLE = "admin"

_PLANNER = frozenset(
    {ProjectPerm.READ, ProjectPerm.UPDATE, ProjectPerm.VENDORS_READ, ProjectPerm.VENDORS_MANAGE}
)
_LEAD = _PLANNER | {ProjectPerm.MANAGE_TEAM, ProjectPerm.ARCHIVE}

PROJECT_ROLE_PERMS: dict[str, frozenset[ProjectPerm]] = {
    ADMIN_PROJECT_ROLE: frozenset(ProjectPerm),
    ProjectRole.LEAD: _LEAD,
    ProjectRole.PLANNER: _PLANNER,
    ProjectRole.VIEWER: frozenset({ProjectPerm.READ, ProjectPerm.VENDORS_READ}),
    ProjectRole.CLIENT: frozenset(),  # couples use the portal API (Sprint 4)
}


def has_perm(role: str, perm: Perm) -> bool:
    try:
        return perm in ROLE_PERMS[OrgRole(role)]
    except ValueError:
        return False


def has_project_perm(project_role: str | None, perm: ProjectPerm) -> bool:
    return project_role is not None and perm in PROJECT_ROLE_PERMS.get(project_role, frozenset())
