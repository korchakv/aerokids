from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import Organization
from app.services.crm import run_billing_renewals


def main() -> None:
    db = SessionLocal()
    try:
        organization_ids = list(db.scalars(select(Organization.id).order_by(Organization.created_at)))
        totals = {
            "organizations": len(organization_ids),
            "resumed_subscriptions": 0,
            "created_subscriptions": 0,
            "skipped_stale_subscriptions": 0,
        }
        for organization_id in organization_ids:
            result = run_billing_renewals(db, organization_id)
            totals["resumed_subscriptions"] += result["resumed_subscriptions"]
            totals["created_subscriptions"] += result["created_subscriptions"]
            totals["skipped_stale_subscriptions"] += result["skipped_stale_subscriptions"]
        print(
            "billing-renewals",
            f"organizations={totals['organizations']}",
            f"resumed={totals['resumed_subscriptions']}",
            f"created={totals['created_subscriptions']}",
            f"stale={totals['skipped_stale_subscriptions']}",
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
