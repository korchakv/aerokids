import type {
  ApiLocation,
  ApiPayment,
  ApiStaff,
  ApiStaffProfile,
  ApiStudentSubscription,
  ApiSubscriptionPlan,
  OperationsBundle,
  Session,
} from "./types";
import { apiGet } from "./client";

export async function loadOperations(session: Session): Promise<OperationsBundle> {
  const membership = session.user.memberships.find((item) => item.organization_id === session.organizationId);
  const role = membership?.role;

  const operationalAccess = ["owner", "admin", "manager", "teacher"].includes(role ?? "");
  const staffAccess = ["owner", "admin"].includes(role ?? "");
  const financeAccess = ["owner", "admin", "accountant"].includes(role ?? "");

  const locationsPromise = operationalAccess
    ? apiGet<ApiLocation[]>("/locations", session)
    : Promise.resolve([]);

  const staffPromise = staffAccess
    ? apiGet<ApiStaff[]>("/staff", session).then(async (items) => Promise.all(
        items.map((item) => apiGet<ApiStaffProfile>(`/staff/${item.id}/profile`, session))
      ))
    : Promise.resolve([]);

  const plansPromise = financeAccess
    ? apiGet<ApiSubscriptionPlan[]>("/subscription-plans", session)
    : Promise.resolve([]);

  const paymentsPromise = financeAccess
    ? apiGet<ApiPayment[]>("/payments", session)
    : Promise.resolve([]);

  const subscriptionsPromise = financeAccess
    ? apiGet<ApiStudentSubscription[]>("/student-subscriptions", session)
    : Promise.resolve([]);

  const [locations, staff, plans, payments, subscriptions] = await Promise.all([
    locationsPromise,
    staffPromise,
    plansPromise,
    paymentsPromise,
    subscriptionsPromise,
  ]);

  return { locations, staff, plans, payments, subscriptions };
}
