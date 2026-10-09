from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import event, inspect

from app.db.session import SessionLocal, engine
from app.models.core import AuditEvent, Group, Organization, Student, StudentStatus


@contextmanager
def select_counter():
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def _seed_registry_rows() -> tuple[str, dict[str, str]]:
    with SessionLocal() as db:
        organization = Organization(name="Performance School", slug="performance-school")
        db.add(organization)
        db.flush()

        db.add_all([
            Student(
                organization_id=organization.id,
                first_name=f"Лід {index}",
                age_at_inquiry=10,
                student_status=StudentStatus.PROSPECT,
            )
            for index in range(80)
        ])
        db.add_all([
            Student(
                organization_id=organization.id,
                first_name=f"Учень {index}",
                age_at_inquiry=11,
                student_status=StudentStatus.ACTIVE,
            )
            for index in range(80)
        ])
        db.add_all([
            Group(
                organization_id=organization.id,
                name=f"Група {index:03d}",
                capacity=8,
                is_active=True,
            )
            for index in range(80)
        ])
        db.add_all([
            AuditEvent(
                organization_id=organization.id,
                entity_type="performance",
                entity_id=organization.id,
                event_type="performance.seeded",
                payload={"index": index},
            )
            for index in range(80)
        ])
        db.commit()
        org_id = str(organization.id)
    return org_id, {"X-Organization-Id": org_id}


def test_paginated_registry_query_counts_are_bounded(client):
    _, headers = _seed_registry_rows()

    with select_counter() as lead_queries:
        response = client.get("/workspace/leads/page?limit=20", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 80
    assert len(response.json()["items"]) == 20
    assert len(lead_queries) <= 4, "\n".join(lead_queries)

    with select_counter() as student_queries:
        response = client.get("/workspace/students/page?limit=20", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 80
    assert len(response.json()["items"]) == 20
    assert len(student_queries) <= 3, "\n".join(student_queries)

    with select_counter() as group_queries:
        response = client.get("/workspace/groups/page?limit=20", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 80
    assert len(response.json()["items"]) == 20
    assert len(group_queries) <= 3, "\n".join(group_queries)

    with select_counter() as audit_queries:
        response = client.get("/audit-events/page?entity_type=performance&limit=20", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 80
    assert len(response.json()["items"]) == 20
    assert len(audit_queries) <= 3, "\n".join(audit_queries)


def test_stage3_composite_indexes_exist_in_test_schema():
    expected = {
        "students": {
            "ix_students_org_status_created",
            "ix_students_org_status_source",
            "ix_students_org_status_next_contact",
        },
        "student_contacts": {"ix_student_contacts_org_student_primary"},
        "trial_lessons": {"ix_trial_lessons_org_student_start"},
        "payments": {"ix_payments_org_status_due_created"},
        "group_staff": {"ix_group_staff_org_group_primary"},
        "audit_events": {
            "ix_audit_events_org_created",
            "ix_audit_events_org_entity_created",
        },
    }
    inspector = inspect(engine)
    for table_name, required in expected.items():
        present = {item["name"] for item in inspector.get_indexes(table_name)}
        assert required <= present, f"{table_name}: missing {required - present}"
