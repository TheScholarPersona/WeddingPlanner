"""Imports every model so that SQLAlchemy relationships and Alembic metadata are complete."""

from app.admin.models import SupportAccessGrant
from app.audit.models import AuditLog
from app.auth.models import PasswordResetToken, RecoveryCode, User, UserSession
from app.budget.models import Budget, BudgetCategory, BudgetItem, Payment
from app.clients.models import Client, ClientContact
from app.documents.models import Document, DocumentVersion
from app.events.models import CalendarFeed, Event
from app.notifications.models import NotificationLog, NotificationPreference
from app.organizations.models import Invitation, Membership, Organization
from app.privacy.models import Consent
from app.projects.models import Project, ProjectMember, ProjectVendor
from app.tasks.models import ActivityEvent, Comment, Milestone, Task, TaskChecklistItem
from app.templates.models import ProjectTemplate, TemplateItem
from app.vendors.models import Vendor

__all__ = [
    "ActivityEvent",
    "AuditLog",
    "Budget",
    "BudgetCategory",
    "BudgetItem",
    "CalendarFeed",
    "Client",
    "ClientContact",
    "Comment",
    "Consent",
    "Document",
    "DocumentVersion",
    "Event",
    "Invitation",
    "Membership",
    "Milestone",
    "NotificationLog",
    "NotificationPreference",
    "Organization",
    "PasswordResetToken",
    "Payment",
    "Project",
    "ProjectMember",
    "ProjectTemplate",
    "ProjectVendor",
    "RecoveryCode",
    "SupportAccessGrant",
    "Task",
    "TaskChecklistItem",
    "TemplateItem",
    "User",
    "UserSession",
    "Vendor",
]
