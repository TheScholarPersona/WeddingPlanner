"""Test data factories. All data is generated with Faker; never use real customer data.

Model factories (organizations, users, projects, ...) are added with their models from Sprint 1.
"""

from faker import Faker

fake = Faker("de_DE")
Faker.seed(20261115)


def couple_display_name() -> str:
    """A fictional couple name such as 'Mia & Tom'."""
    return f"{fake.first_name()} & {fake.first_name()}"


def safe_email() -> str:
    """An address on a reserved example domain, so no real mailbox is ever contacted."""
    return str(fake.unique.safe_email())
