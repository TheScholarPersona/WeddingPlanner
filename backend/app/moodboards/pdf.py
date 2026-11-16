"""Moodboard PDF for vendors (florist, baker, ...): images, captions and the color palette.

Privacy defaults: no comments, hearts, internal notes or uploader names, and the couple's
name only when the planner asks for it. Made with WeasyPrint from an HTML template.
"""

import base64
import html
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weasyprint import HTML

from app.audit import service as audit
from app.authz.deps import ProjectContext, not_found
from app.documents.storage import get_storage
from app.moodboards.models import ItemStatus, Moodboard, MoodboardItem, MoodboardSection
from app.organizations.models import Organization

FONTS = Path(__file__).parent / "fonts"


def _e(value: str | None) -> str:
    return html.escape(value or "")


def _date(value: date | None, locale: str) -> str:
    if value is None:
        return ""
    return value.strftime("%d.%m.%Y") if locale.startswith("de") else value.strftime("%d %b %Y")


STYLE = (Path(__file__).parent / "pdf.css").read_text().replace("{FONTS}", FONTS.as_uri())


async def render(
    db: AsyncSession,
    ctx: ProjectContext,
    board_id: uuid.UUID,
    *,
    selected_only: bool,
    section_id: uuid.UUID | None,
    include_couple: bool,
) -> tuple[str, bytes]:
    board = (
        await db.execute(
            select(Moodboard).where(
                Moodboard.id == board_id, Moodboard.project_id == ctx.project.id
            )
        )
    ).scalar_one_or_none()
    if board is None:
        raise not_found()
    org = await db.get(Organization, ctx.organization_id)
    assert org is not None
    sections = list(
        (
            await db.execute(
                select(MoodboardSection)
                .where(MoodboardSection.board_id == board.id)
                .order_by(MoodboardSection.position, MoodboardSection.created_at)
            )
        ).scalars()
    )
    if section_id is not None:
        sections = [s for s in sections if s.id == section_id]
        if not sections:
            raise not_found()
    statuses = (
        [ItemStatus.SELECTED] if selected_only else [ItemStatus.SELECTED, ItemStatus.PROPOSED]
    )
    items = list(
        (
            await db.execute(
                select(MoodboardItem)
                .where(
                    MoodboardItem.board_id == board.id,
                    MoodboardItem.status.in_(statuses),
                    MoodboardItem.display_key.is_not(None),
                )
                .order_by(MoodboardItem.position, MoodboardItem.created_at)
            )
        ).scalars()
    )
    storage = get_storage()
    groups: list[tuple[str, list[MoodboardItem]]] = [
        (s.title, [i for i in items if i.section_id == s.id]) for s in sections
    ]
    if section_id is None:
        groups.append(("More ideas", [i for i in items if i.section_id is None]))

    parts: list[str] = []
    for title, group in groups:
        if not group:
            continue
        figures = []
        for item in group:
            data = base64.b64encode(await storage.get(item.display_key or "")).decode()
            figures.append(
                f'<figure><img src="data:image/webp;base64,{data}" alt="{_e(item.caption)}">'
                f"<figcaption>{_e(item.caption)}</figcaption></figure>"
            )
        parts.append(
            f'<section><h2>{_e(title)}</h2><div class="grid">{"".join(figures)}</div></section>'
        )

    project = ctx.project
    who = _e(project.title) if include_couple else "Wedding"
    when = _date(project.wedding_date, org.locale)
    meta = " · ".join(p for p in (f"{who} on {when}" if when else who, _e(project.venue_name)) if p)
    palette = "".join(
        f'<div class="swatch"><div class="chip" style="background:{_e(c)}"></div>'
        f'<div class="hex">{_e(c).upper()}</div></div>'
        for c in board.palette or []
        if isinstance(c, str) and len(c) == 7 and c.startswith("#")
    )
    count = sum(len(g) for _, g in groups)
    scope = "selected images" if selected_only else "all current ideas"
    footer = f"{count} image{'s' if count != 1 else ''} · {scope}"
    body = f"""<!doctype html><html><head><meta charset="utf-8"><style>{STYLE}</style></head><body>
<div class="cover">
  <div class="eyebrow">{_e(org.name)} · Moodboard</div>
  <h1>{_e(board.title)}</h1>
  <div class="meta">{meta}</div>
  {f'<div class="palette">{palette}</div>' if palette else ""}
  <div class="footer">{footer}</div>
</div>
{"".join(parts) or "<section><h2>No images yet</h2></section>"}
</body></html>"""
    pdf = HTML(string=body).write_pdf()
    await audit.record(
        db,
        action="moodboard.exported",
        resource_type="moodboard",
        resource_id=board.id,
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user.id,
        changes={"images": {"new": count}, "with_couple_name": {"new": include_couple}},
    )
    safe = "".join(c if c.isalnum() else "-" for c in board.title).strip("-")[:40] or "moodboard"
    return f"moodboard-{safe}.pdf", pdf
