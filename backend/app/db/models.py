"""Imports every model so that SQLAlchemy relationships and Alembic metadata are complete."""

from app.audit.models import AuditLog
from app.auth.models import PasswordResetToken, User, UserSession
from app.budget.models import Budget, BudgetCategory, BudgetItem, Payment
from app.clients.models import Client, ClientContact
from app.documents.models import Document, DocumentVersion
from app.events.models import CalendarFeed, Event
from app.notifications.models import NotificationLog, NotificationPreference
from app.organizations.models import Invitation, Membership, Organization
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
    "Task",
    "TaskChecklistItem",
    "TemplateItem",
    "User",
    "UserSession",
    "Vendor",
]
