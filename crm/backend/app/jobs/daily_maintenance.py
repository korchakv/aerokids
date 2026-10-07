from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import Group, Organization
from app.services import billing_hardening, hardening, notifications


def run_daily_maintenance() -> dict:
    db = SessionLocal()
    results = []
    try:
        organizations = list(db.scalars(select(Organization).order_by(Organization.name)))
        for organization in organizations:
            org_result = {
                "organization_id": str(organization.id),
                "organization_name": organization.name,
                "reconciled_groups": 0,
                "created_lesson_sessions": 0,
                "billing": None,
                "errors": [],
            }
            try:
                groups = list(db.scalars(select(Group).where(
                    Group.organization_id == organization.id,
                    Group.is_active.is_(True),
                ).order_by(Group.name)))
                for group in groups:
                    try:
                        created = hardening.reconcile_group_future_sessions(
                            db,
                            organization.id,
                            group,
                            actor_user_id=None,
                        )
                        db.commit()
                        org_result["reconciled_groups"] += 1
                        org_result["created_lesson_sessions"] += created
                    except Exception as exc:
                        db.rollback()
                        org_result["errors"].append({"group": group.name, "error": str(exc)})
                try:
                    org_result["billing"] = billing_hardening.run_renewals(
                        db,
                        organization.id,
                        through_date=None,
                        actor_user_id=None,
                    )
                except Exception as exc:
                    db.rollback()
                    org_result["errors"].append({"billing": str(exc)})
            except Exception as exc:
                db.rollback()
                org_result["errors"].append({"organization": str(exc)})
            results.append(org_result)

        cleanup_before = datetime.now(timezone.utc) - timedelta(days=7)
        cleanup = hardening.cleanup_stale_throttles(db, cleanup_before)
        email_delivery = notifications.deliver_pending(db)
        return {
            "organizations": results,
            "throttle_cleanup": cleanup,
            "transactional_email": email_delivery,
        }
    finally:
        db.close()


if __name__ == "__main__":
    print(json.dumps(run_daily_maintenance(), ensure_ascii=False, indent=2, default=str))
