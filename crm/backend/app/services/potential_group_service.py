from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import CrmStatus, Organization, PotentialGroupProposal, Student, StudentStatus
from app.services.audit_service import record_audit


def _validate_members(db: Session, org_id: UUID, data, existing_ids=()) -> list[dict]:
    members = []
    for member in data.members:
        student = db.scalar(select(Student).where(Student.id == member.student_id, Student.organization_id == org_id))
        if student is None or (str(student.id) not in existing_ids and (
            student.student_status != StudentStatus.PROSPECT or student.crm_status in (CrmStatus.DECLINED, CrmStatus.NOT_RELEVANT)
        )):
            raise HTTPException(status_code=422, detail="До підбору можна додати лише відкриті заявки цієї організації")
        members.append(member.model_dump(mode="json"))
    return members


def list_proposals(db: Session, org_id: UUID) -> list[PotentialGroupProposal]:
    return list(db.scalars(select(PotentialGroupProposal).where(
        PotentialGroupProposal.organization_id == org_id,
    ).order_by(PotentialGroupProposal.created_at.desc())))


def _schedule_key(slots):
    return sorted((s["weekday"], s["start_time"][:5], s["end_time"][:5]) for s in slots)


def create_proposal(db: Session, org_id: UUID, user_id: UUID, data) -> PotentialGroupProposal:
    if len(data.members) < 2:
        raise HTTPException(status_code=422, detail="Для потенційної групи потрібно щонайменше двоє учнів")
    # Serialize saves for one organization so repeated clicks cannot create duplicates.
    db.scalar(select(Organization).where(Organization.id == org_id).with_for_update())
    members = _validate_members(db, org_id, data)
    ids = sorted(m["student_id"] for m in members)
    for saved in list_proposals(db, org_id):
        if not saved.formed_group_id and sorted(m["student_id"] for m in saved.members) == ids:
            return saved
    selected = [slot.model_dump(mode="json") for slot in data.selected_slots]
    if len(selected) < 2 and any(m["response"] == "agreed" for m in members):
        raise HTTPException(status_code=422, detail="Спочатку оберіть конкретний графік")
    proposal = PotentialGroupProposal(
        organization_id=org_id, created_by=user_id, members=members,
        slots=[slot.model_dump(mode="json") for slot in data.slots],
        selected_slots=selected, schedule_history=[], version=1, stale=data.stale,
    )
    db.add(proposal)
    db.flush()
    record_audit(db, org_id, "potential_group_proposal", proposal.id, "potential_group_proposal.saved", {
        "member_count": len(members), "selected_slots": selected,
    }, actor_user_id=user_id)
    db.commit()
    db.refresh(proposal)
    return proposal


def update_proposal(db: Session, org_id: UUID, proposal_id: UUID, user_id: UUID, data) -> PotentialGroupProposal:
    proposal = db.scalar(select(PotentialGroupProposal).where(
        PotentialGroupProposal.id == proposal_id, PotentialGroupProposal.organization_id == org_id,
    ).with_for_update())
    if proposal is None:
        raise HTTPException(status_code=404, detail="Потенційну групу не знайдено")
    if proposal.formed_group_id:
        raise HTTPException(status_code=409, detail="З цієї пропозиції вже створено групу")
    if (proposal.selected_slots and data.version is None) or (data.version is not None and data.version != proposal.version):
        raise HTTPException(status_code=409, detail="Пропозицію змінили в іншому вікні. Оновіть список перед редагуванням")
    before = {"members": proposal.members, "slots": proposal.selected_slots, "stale": proposal.stale}
    members = _validate_members(db, org_id, data, {m["student_id"] for m in proposal.members})
    selected = [slot.model_dump(mode="json") for slot in data.selected_slots]
    changed = _schedule_key(selected) != _schedule_key(proposal.selected_slots)
    previous = {m["student_id"]: m for m in proposal.members}
    for member in members:
        prior = previous.get(member["student_id"], {})
        if prior.get("response") == "agreed" and member["response"] == "agreed" and (changed or prior.get("availability_snapshot") != member["availability_snapshot"]):
            member["response"] = "reconfirm"
    if len(selected) < 2 and any(m["response"] == "agreed" for m in members):
        raise HTTPException(status_code=422, detail="Спочатку оберіть конкретний графік")
    if changed or any(previous.get(m["student_id"], {}).get("response") != m["response"] for m in members):
        proposal.schedule_history = [*proposal.schedule_history, {
            "at": datetime.now(timezone.utc).isoformat(), "before": proposal.selected_slots,
            "after": selected, "responses": [{"student_id": m["student_id"], "response": m["response"]} for m in proposal.members],
            "after_responses": [{"student_id": m["student_id"], "response": m["response"]} for m in members],
        }]
    proposal.members = members
    proposal.slots = [slot.model_dump(mode="json") for slot in data.slots]
    proposal.selected_slots = selected
    proposal.stale = data.stale
    proposal.version += 1
    record_audit(db, org_id, "potential_group_proposal", proposal.id, "potential_group_proposal.updated", {
        "before": before, "after": {"members": members, "slots": selected, "stale": data.stale},
    }, actor_user_id=user_id)
    db.commit()
    db.refresh(proposal)
    return proposal


def preview_conflicts(db: Session, org_id: UUID, data) -> list[str]:
    from app.models.core import Location
    from app.services.hardening import organization_today, organization_timezone, resource_conflict_reason
    if data.location_id and not db.scalar(select(Location.id).where(Location.id == data.location_id, Location.organization_id == org_id)):
        raise HTTPException(status_code=404, detail="Локацію не знайдено")
    today = organization_today(db, org_id)
    tz = organization_timezone(db, org_id)
    conflicts = set()
    for slot in data.slots:
        first = today + timedelta(days=(slot.weekday - today.weekday()) % 7)
        for week in range(9):
            start = datetime.combine(first + timedelta(weeks=week), slot.start_time, tzinfo=tz)
            duration = (slot.end_time.hour * 60 + slot.end_time.minute) - (slot.start_time.hour * 60 + slot.start_time.minute)
            reason = resource_conflict_reason(db, org_id, start, duration, data.location_id, None, None)
            if reason:
                conflicts.add(reason)
    return sorted(conflicts)
