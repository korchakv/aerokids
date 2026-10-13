from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import CrmStatus, PotentialGroupProposal, Student
from app.services.audit_service import record_audit


def _validate_members(db: Session, org_id: UUID, proposal, waiting_only: bool) -> list[dict]:
    members = []
    for member in proposal.members:
        student = db.scalar(select(Student).where(
            Student.id == member.student_id,
            Student.organization_id == org_id,
            *([Student.crm_status == CrmStatus.WAITING_FOR_GROUP] if waiting_only else []),
        ))
        if student is None:
            raise HTTPException(status_code=422, detail="Усі учасники мають очікувати групу в цій організації")
        members.append(member.model_dump(mode="json"))
    return members


def list_proposals(db: Session, org_id: UUID) -> list[PotentialGroupProposal]:
    return list(db.scalars(select(PotentialGroupProposal).where(
        PotentialGroupProposal.organization_id == org_id,
    ).order_by(PotentialGroupProposal.created_at.desc())))


def create_proposal(db: Session, org_id: UUID, user_id: UUID, data) -> PotentialGroupProposal:
    if len(data.members) < 2:
        raise HTTPException(status_code=422, detail="Для потенційної групи потрібно щонайменше двоє учнів")
    proposal = PotentialGroupProposal(
        organization_id=org_id,
        created_by=user_id,
        members=_validate_members(db, org_id, data, waiting_only=True),
        slots=[slot.model_dump(mode="json") for slot in data.slots],
        stale=data.stale,
    )
    db.add(proposal)
    db.flush()
    record_audit(db, org_id, "potential_group_proposal", proposal.id, "potential_group_proposal.saved", {
        "member_count": len(proposal.members), "slots": proposal.slots,
    }, actor_user_id=user_id)
    db.commit()
    db.refresh(proposal)
    return proposal


def update_proposal(db: Session, org_id: UUID, proposal_id: UUID, user_id: UUID, data) -> PotentialGroupProposal:
    proposal = db.scalar(select(PotentialGroupProposal).where(
        PotentialGroupProposal.id == proposal_id,
        PotentialGroupProposal.organization_id == org_id,
    ))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Потенційну групу не знайдено")
    before = {"members": proposal.members, "slots": proposal.slots, "stale": proposal.stale}
    proposal.members = _validate_members(db, org_id, data, waiting_only=False)
    proposal.slots = [slot.model_dump(mode="json") for slot in data.slots]
    proposal.stale = data.stale
    record_audit(db, org_id, "potential_group_proposal", proposal.id, "potential_group_proposal.updated", {
        "before": before,
        "after": {"members": proposal.members, "slots": proposal.slots, "stale": proposal.stale},
    }, actor_user_id=user_id)
    previous_responses = {item["student_id"]: item.get("response", "not_contacted") for item in before["members"]}
    response_changes = [{
        "student_id": item["student_id"],
        "before": previous_responses.get(item["student_id"], "not_contacted"),
        "after": item.get("response", "not_contacted"),
    } for item in proposal.members if previous_responses.get(item["student_id"], "not_contacted") != item.get("response", "not_contacted")]
    if response_changes:
        record_audit(db, org_id, "potential_group_proposal", proposal.id, "potential_group_proposal.parent_response_updated", {
            "responses": response_changes,
        }, actor_user_id=user_id)
    db.commit()
    db.refresh(proposal)
    return proposal
