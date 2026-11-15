"""Imports every model so that SQLAlchemy relationships and Alembic metadata are complete."""

from app.audit.models import AuditLog
from app.auth.models import PasswordResetToken, User, UserSession
from app.clients.models import Client, ClientContact
from app.organizations.models import Invitation, Membership, Organization
from app.projects.models import Project, ProjectMember, ProjectVendor
from app.tasks.models import Milestone, Task
from app.templates.models import ProjectTemplate, TemplateItem
from app.vendors.models import Vendor

__all__ = [
    "AuditLog",
    "Client",
    "ClientContact",
    "Invitation",
    "Membership",
    "Milestone",
    "Organization",
    "PasswordResetToken",
    "Project",
    "ProjectMember",
    "ProjectTemplate",
    "ProjectVendor",
    "Task",
    "TemplateItem",
    "User",
    "UserSession",
    "Vendor",
]
