from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Literal
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import Attendance, AttendanceStatus, Enrollment, EnrollmentStatus, Group, LessonSession, LessonStatus, StaffRole, Student
from app.models.learning import CurriculumLesson, CurriculumMaterial, StudentLessonCompletion
from app.services import hardening
from app.services.crm import record_audit


router = APIRouter(tags=["learning"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _require_teaching(access: OrgAccess) -> None:
    if access.role == StaffRole.ACCOUNTANT:
        raise HTTPException(status_code=403, detail="Insufficient role for this action")


def _require_lesson(db: Session, org_id: uuid.UUID, lesson_id: uuid.UUID) -> CurriculumLesson:
    lesson = db.scalar(select(CurriculumLesson).where(
        CurriculumLesson.organization_id == org_id,
        CurriculumLesson.id == lesson_id,
    ))
    if lesson is None:
        raise HTTPException(status_code=404, detail="Curriculum lesson not found")
    return lesson


def _safe_filename(value: str) -> str:
    return re.sub(r"[^\w.() -]", "_", value, flags=re.UNICODE).strip(" .")[:255] or "material"


class LessonWrite(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    outline: str | None = Field(default=None, max_length=12000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Title cannot be empty")
        return value


class MaterialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    kind: Literal["link", "file"]
    url: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None


class LessonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    position: int
    title: str
    outline: str | None
    materials: list[MaterialRead] = Field(default_factory=list)


class MaterialLinkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    url: str = Field(min_length=8, max_length=2000)

    @field_validator("url")
    @classmethod
    def valid_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Material URL must use http or https")
        return value


class CompletionUpdate(BaseModel):
    completed: bool
    note: str | None = Field(default=None, max_length=300)


class BaselineUpdate(BaseModel):
    completed_through: int = Field(ge=0, le=10000)


class CurriculumAssignment(BaseModel):
    lesson_id: uuid.UUID | None = None


@router.get("/curriculum-lessons", response_model=list[LessonRead])
def list_curriculum_lessons(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    lessons = list(db.scalars(select(CurriculumLesson).where(
        CurriculumLesson.organization_id == access.organization_id,
    ).order_by(CurriculumLesson.position, CurriculumLesson.created_at)))
    for lesson in lessons:
        lesson.materials = list(db.scalars(select(CurriculumMaterial).where(
            CurriculumMaterial.organization_id == access.organization_id,
            CurriculumMaterial.lesson_id == lesson.id,
        ).order_by(CurriculumMaterial.created_at)))
    return lessons


@router.post("/curriculum-lessons", response_model=LessonRead, status_code=201)
def create_curriculum_lesson(data: LessonWrite, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    current = list(db.scalars(select(CurriculumLesson).where(
        CurriculumLesson.organization_id == access.organization_id,
    ).order_by(CurriculumLesson.position)))
    position = current[-1].position + 1 if current else 1
    lesson = CurriculumLesson(organization_id=access.organization_id, position=position, title=data.title, outline=data.outline)
    db.add(lesson)
    db.flush()
    record_audit(db, access.organization_id, "curriculum_lesson", lesson.id, "curriculum_lesson.created", {"position": position}, access.user_id)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.patch("/curriculum-lessons/{lesson_id}", response_model=LessonRead)
def update_curriculum_lesson(lesson_id: uuid.UUID, data: LessonWrite, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    lesson = _require_lesson(db, access.organization_id, lesson_id)
    lesson.title = data.title
    lesson.outline = data.outline
    record_audit(db, access.organization_id, "curriculum_lesson", lesson.id, "curriculum_lesson.updated", {"position": lesson.position}, access.user_id)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.delete("/curriculum-lessons/{lesson_id}", status_code=204)
def delete_curriculum_lesson(lesson_id: uuid.UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    lesson = _require_lesson(db, access.organization_id, lesson_id)
    linked = db.scalar(select(LessonSession.id).where(
        LessonSession.organization_id == access.organization_id,
        LessonSession.curriculum_lesson_id == lesson.id,
    ).limit(1))
    if linked:
        raise HTTPException(status_code=409, detail="This curriculum lesson is linked to class history")
    position = lesson.position
    db.delete(lesson)
    db.flush()
    for group in db.scalars(select(Group).where(
        Group.organization_id == access.organization_id,
        Group.curriculum_completed_through >= position,
    )):
        group.curriculum_completed_through -= 1
    shifted = list(db.scalars(select(CurriculumLesson).where(
        CurriculumLesson.organization_id == access.organization_id,
        CurriculumLesson.position > position,
    ).order_by(CurriculumLesson.position)))
    for row in shifted:
        row.position += 10000
    db.flush()
    for row in shifted:
        row.position -= 10001
    db.commit()
    return Response(status_code=204)


@router.post("/curriculum-lessons/{lesson_id}/materials/link", response_model=MaterialRead, status_code=201)
def add_material_link(lesson_id: uuid.UUID, data: MaterialLinkCreate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    _require_lesson(db, access.organization_id, lesson_id)
    material = CurriculumMaterial(
        organization_id=access.organization_id, lesson_id=lesson_id, title=data.title.strip(), kind="link", url=data.url,
    )
    db.add(material)
    db.flush()
    record_audit(db, access.organization_id, "curriculum_material", material.id, "curriculum_material.created", {"lesson_id": str(lesson_id), "kind": "link", "title": material.title}, access.user_id)
    db.commit()
    db.refresh(material)
    return material


@router.post("/curriculum-lessons/{lesson_id}/materials/file", response_model=MaterialRead, status_code=201)
async def upload_material(lesson_id: uuid.UUID, title: str = Form(..., min_length=1, max_length=240), file: UploadFile = File(...), access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    _require_lesson(db, access.organization_id, lesson_id)
    content_type = (file.content_type or "application/octet-stream").lower()
    filename = _safe_filename(file.filename or "material")
    allowed = {
        "application/pdf", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.ms-powerpoint", "image/jpeg", "image/png", "image/webp", "video/mp4",
    }
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail="Upload a PDF, PowerPoint, JPG, PNG, WebP, or MP4 file")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File must be between 1 byte and 20 MB")
    material = CurriculumMaterial(
        organization_id=access.organization_id, lesson_id=lesson_id, title=title.strip(), kind="file",
        filename=filename, content_type=content_type, size_bytes=len(content), file_data=content,
    )
    db.add(material)
    db.flush()
    record_audit(db, access.organization_id, "curriculum_material", material.id, "curriculum_material.created", {"lesson_id": str(lesson_id), "kind": "file", "filename": filename, "size_bytes": len(content)}, access.user_id)
    db.commit()
    db.refresh(material)
    return material


@router.get("/curriculum-lessons/{lesson_id}/materials/{material_id}/file")
def download_material(lesson_id: uuid.UUID, material_id: uuid.UUID, inline: bool = False, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    material = db.scalar(select(CurriculumMaterial).where(
        CurriculumMaterial.organization_id == access.organization_id,
        CurriculumMaterial.lesson_id == lesson_id,
        CurriculumMaterial.id == material_id,
        CurriculumMaterial.kind == "file",
    ))
    if material is None or material.file_data is None:
        raise HTTPException(status_code=404, detail="Material not found")
    inline_types = {"application/pdf", "image/jpeg", "image/png", "image/webp", "video/mp4"}
    disposition = "inline" if inline and material.content_type in inline_types else "attachment"
    safe_name = quote(material.filename or "material", safe="")
    return Response(
        content=material.file_data,
        media_type=material.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="material"; filename*=UTF-8\'\'{safe_name}', "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/curriculum-lessons/{lesson_id}/materials/{material_id}", status_code=204)
def delete_material(lesson_id: uuid.UUID, material_id: uuid.UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    material = db.scalar(select(CurriculumMaterial).where(
        CurriculumMaterial.organization_id == access.organization_id,
        CurriculumMaterial.lesson_id == lesson_id,
        CurriculumMaterial.id == material_id,
    ))
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    record_audit(db, access.organization_id, "curriculum_material", material.id, "curriculum_material.deleted", {"lesson_id": str(lesson_id), "title": material.title}, access.user_id)
    db.delete(material)
    db.commit()
    return Response(status_code=204)


@router.put("/lesson-sessions/{session_id}/curriculum-lesson")
def assign_curriculum_lesson(session_id: uuid.UUID, data: CurriculumAssignment, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    session = db.scalar(select(LessonSession).where(
        LessonSession.organization_id == access.organization_id,
        LessonSession.id == session_id,
    ))
    if session is None:
        raise HTTPException(status_code=404, detail="Lesson session not found")
    hardening.ensure_group_access(db, access.organization_id, access.user_id, access.role, session.group_id)
    title = None
    if data.lesson_id is not None:
        lesson = _require_lesson(db, access.organization_id, data.lesson_id)
        session.curriculum_lesson_id = lesson.id
        session.topic = lesson.title
        title = lesson.title
    else:
        session.curriculum_lesson_id = None
        session.topic = None
    record_audit(db, access.organization_id, "lesson_session", session.id, "lesson.curriculum_assigned", {
        "curriculum_lesson_id": str(session.curriculum_lesson_id) if session.curriculum_lesson_id else None,
        "topic": session.topic,
    }, access.user_id)
    db.commit()
    return {"session_id": session.id, "curriculum_lesson_id": session.curriculum_lesson_id, "topic": session.topic or "", "lesson_title": title}


@router.put("/groups/{group_id}/learning-baseline")
def set_group_learning_baseline(group_id: uuid.UUID, data: BaselineUpdate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    group = db.scalar(select(Group).where(Group.organization_id == access.organization_id, Group.id == group_id))
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_teaching(access)
    if access.role == StaffRole.TEACHER:
        hardening.ensure_group_access(db, access.organization_id, access.user_id, access.role, group.id)
    group.curriculum_completed_through = data.completed_through
    group.curriculum_baseline_date = hardening.organization_today(db, access.organization_id)
    record_audit(db, access.organization_id, "group", group.id, "learning.baseline_set", {"completed_through": data.completed_through}, access.user_id)
    db.commit()
    return {"group_id": group.id, "completed_through": group.curriculum_completed_through, "baseline_date": group.curriculum_baseline_date}


@router.get("/groups/{group_id}/learning-baseline")
def get_group_learning_baseline(group_id: uuid.UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    group = db.scalar(select(Group).where(Group.organization_id == access.organization_id, Group.id == group_id))
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    hardening.ensure_group_access(db, access.organization_id, access.user_id, access.role, group.id)
    return {"group_id": group.id, "completed_through": group.curriculum_completed_through, "baseline_date": group.curriculum_baseline_date}


@router.get("/students/{student_id}/learning-progress")
def student_learning_progress(student_id: uuid.UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    student = db.scalar(select(Student).where(Student.organization_id == access.organization_id, Student.id == student_id))
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == access.organization_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    ).order_by(Enrollment.started_at.desc())))
    allowed_groups = None
    if access.role == StaffRole.TEACHER:
        allowed_groups = hardening.strict_group_ids_for_user(db, access.organization_id, access.user_id, access.role) or set()
        enrollments = [enrollment for enrollment in enrollments if enrollment.group_id in allowed_groups]
        if not any(enrollment.group_id in allowed_groups for enrollment in enrollments):
            # Former students remain visible through attended teaching history.
            session_group = db.scalar(select(LessonSession.group_id).join(
                Attendance, Attendance.session_id == LessonSession.id,
            ).where(
                Attendance.organization_id == access.organization_id,
                Attendance.student_id == student.id,
                LessonSession.group_id.in_(allowed_groups),
            ).limit(1)) if allowed_groups else None
            if session_group is None:
                raise HTTPException(status_code=403, detail="No access to this student")

    lessons = list(db.scalars(select(CurriculumLesson).where(
        CurriculumLesson.organization_id == access.organization_id,
    ).order_by(CurriculumLesson.position)))
    manual_ids = set(db.scalars(select(StudentLessonCompletion.lesson_id).where(
        StudentLessonCompletion.organization_id == access.organization_id,
        StudentLessonCompletion.student_id == student.id,
    )))
    attended_sessions = list(db.scalars(select(LessonSession).join(
        Attendance, Attendance.session_id == LessonSession.id,
    ).where(
        Attendance.organization_id == access.organization_id,
        Attendance.student_id == student.id,
        LessonSession.organization_id == access.organization_id,
        LessonSession.curriculum_lesson_id.is_not(None),
    )))
    if allowed_groups is not None:
        attended_sessions = [row for row in attended_sessions if row.group_id in allowed_groups]
    group_ids = {enrollment.group_id for enrollment in enrollments} | {row.group_id for row in attended_sessions}
    sessions = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == access.organization_id,
        LessonSession.curriculum_lesson_id.is_not(None),
        LessonSession.group_id.in_(group_ids),
    ))) if group_ids else []
    attendance_by_session = {}
    if sessions:
        attendance_by_session = {row.session_id: row.status for row in db.scalars(select(Attendance).where(
            Attendance.organization_id == access.organization_id,
            Attendance.student_id == student.id,
            Attendance.session_id.in_([session.id for session in sessions]),
        ))}
    started_by_group = {row.group_id: row.started_at for row in enrollments}
    baseline_by_group = {
        row.id: (row.curriculum_completed_through, row.curriculum_baseline_date)
        for row in db.scalars(select(Group).where(
            Group.organization_id == access.organization_id,
            Group.id.in_({session.group_id for session in sessions} | {e.group_id for e in enrollments}),
        ))
    }
    by_lesson: dict[uuid.UUID, list[tuple[LessonSession, AttendanceStatus | None]]] = {}
    for session in sessions:
        by_lesson.setdefault(session.curriculum_lesson_id, []).append((session, attendance_by_session.get(session.id)))
    result = []
    for lesson in lessons:
        related = [(session, status) for session, status in by_lesson.get(lesson.id, []) if session.status == LessonStatus.COMPLETED]
        after_join: list[tuple[LessonSession, AttendanceStatus | None]] = []
        had_pre_join_session = False
        for session, _ in related:
            start = started_by_group.get(session.group_id)
            if start is not None and session.starts_at.date() < start:
                had_pre_join_session = True
            else:
                after_join.append((session, attendance_by_session.get(session.id)))
        attended = any(status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE} for _, status in related)
        missed = any(status in {AttendanceStatus.ABSENT, AttendanceStatus.EXCUSED} for _, status in after_join)
        before_join = had_pre_join_session and not after_join
        baseline_complete = any(
            lesson.position <= order and baseline_date is not None
            and started_by_group.get(group_id) is not None
            and started_by_group[group_id] <= baseline_date
            for group_id, (order, baseline_date) in baseline_by_group.items()
        )
        baseline_before_join = any(
            lesson.position <= order and baseline_date is not None
            and started_by_group.get(group_id) is not None
            and started_by_group[group_id] > baseline_date
            for group_id, (order, baseline_date) in baseline_by_group.items()
        )
        if lesson.id in manual_ids or attended or baseline_complete:
            status = "completed"
        elif related and missed and not before_join:
            status = "missed"
        elif before_join or baseline_before_join:
            status = "before_join"
        else:
            status = "not_started"
        result.append({
            "lesson_id": lesson.id,
            "position": lesson.position,
            "title": lesson.title,
            "status": status,
            "manual_completion": lesson.id in manual_ids,
            "automatic_completion": attended or baseline_complete,
        })
    return result


@router.put("/students/{student_id}/learning-progress/{lesson_id}")
def set_student_lesson_completion(student_id: uuid.UUID, lesson_id: uuid.UUID, data: CompletionUpdate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    _require_teaching(access)
    student = db.scalar(select(Student).where(Student.organization_id == access.organization_id, Student.id == student_id))
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    lesson = _require_lesson(db, access.organization_id, lesson_id)
    if access.role == StaffRole.TEACHER:
        groups = hardening.strict_group_ids_for_user(db, access.organization_id, access.user_id, access.role) or set()
        enrollment = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == access.organization_id,
            Enrollment.student_id == student.id,
            Enrollment.group_id.in_(groups),
            Enrollment.status == EnrollmentStatus.ACTIVE,
        ).limit(1)) if groups else None
        if enrollment is None:
            raise HTTPException(status_code=403, detail="No access to this student")
    row = db.scalar(select(StudentLessonCompletion).where(
        StudentLessonCompletion.organization_id == access.organization_id,
        StudentLessonCompletion.student_id == student.id,
        StudentLessonCompletion.lesson_id == lesson.id,
    ))
    if data.completed and row is None:
        row = StudentLessonCompletion(
            organization_id=access.organization_id, student_id=student.id, lesson_id=lesson.id,
            completed_by_user_id=access.user_id, note=data.note,
        )
        db.add(row)
    elif data.completed and row is not None:
        row.note = data.note
        row.completed_by_user_id = access.user_id
    elif not data.completed and row is not None:
        db.delete(row)
    record_audit(db, access.organization_id, "student", student.id, "learning.progress_updated", {
        "lesson_id": str(lesson.id), "completed": data.completed,
    }, access.user_id)
    db.commit()
    return {"student_id": student.id, "lesson_id": lesson.id, "completed": data.completed}
