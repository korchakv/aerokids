import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";

test("potential groups keep one selected schedule and require renewed consent", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.getByLabel("Email").fill("owner@smoke.test");
  await page.getByLabel("Пароль").fill("smoke-test-password-123");
  await page.getByRole("button", { name: "Увійти" }).click();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
  const suffix = randomUUID();
  const names = [`Підбір Анна ${suffix}`, `Підбір Богдан ${suffix}`];
  await page.evaluate(async (names) => {
    const session = JSON.parse(sessionStorage.getItem("school-crm-session")!);
    const headers = { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}`, "X-Organization-Id": session.organizationId };
    const request = async (path: string, method: string, body: unknown) => {
      const response = await fetch(`/api${path}`, { method, headers, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    };
    const availability = [2, 4].map((weekday) => ({ weekday, start_time: "08:00", end_time: "11:00", preference: "preferred" }));
    const ids = [];
    for (const name of names) {
      const student = await request("/students", "POST", { first_name: name, age_at_inquiry: 11 });
      await request(`/students/${student.id}/lead-outcome`, "PATCH", { crm_status: "waiting_for_group" });
      const preferences = await request(`/students/${student.id}/preferences`, "PUT", { preferred_location_id: null, availability });
      if (preferences.availability.length !== availability.length) throw new Error("Не збереглися всі тестові дні доступності");
      ids.push(student.id);
    }
    const selectedSlots = availability.map((slot) => ({ ...slot, end_time: "09:00", exact_match: true }));
    await request("/groups/potential-proposals", "POST", {
      members: ids.map((student_id) => ({ student_id, response: "not_contacted", availability_snapshot: availability })),
      slots: selectedSlots,
      selected_slots: selectedSlots,
    });
  }, names);
  await page.reload();
  await page.getByText("Групи", { exact: true }).first().click();
  const card = page.getByTestId("potential-proposal").filter({ hasText: names[0] }).first();
  await expect(card).toBeVisible();
  await expect(card.getByText("Середа 08:00–11:00", { exact: true })).toBeVisible();
  await expect(card.locator(".potentialSelected")).toContainText("П’ятниця 08:00–09:00");
  await card.locator(".potentialPeople > summary").first().click();
  for (const name of names) await card.getByLabel(`Відповідь батьків: ${name}`, { exact: true }).selectOption("agreed");
  await card.getByRole("button", { name: "Зберегти пропозицію" }).click();
  await expect(card.getByRole("button", { name: "Створити групу · 2 погоджених" })).toBeEnabled();
  await card.getByRole("button", { name: "Редагувати графік" }).click();
  await card.getByLabel("Початок", { exact: true }).first().selectOption("09:00");
  await expect(card.getByRole("button", { name: "Створити групу · 0 погоджених" })).toBeDisabled();
  await card.getByRole("button", { name: "Зберегти пропозицію" }).click();
  await expect(card.getByText("Збережено", { exact: true })).toBeVisible();
  await page.reload();
  await page.getByText("Групи", { exact: true }).first().click();
  await expect(card.locator(".potentialSelected")).toContainText("Середа 09:00–10:00");
  await card.locator(".potentialPeople > summary").first().click();
  for (const name of names) {
    await expect(card.getByLabel(`Відповідь батьків: ${name}`, { exact: true })).toHaveValue("reconfirm");
    await card.getByLabel(`Відповідь батьків: ${name}`, { exact: true }).selectOption("agreed");
  }
  await card.getByRole("button", { name: "Зберегти пропозицію" }).click();
  await expect(card.getByRole("button", { name: "Створити групу · 2 погоджених" })).toBeEnabled();
  await card.screenshot({ path: testInfo.outputPath("potential-group.png") });
  await card.getByRole("button", { name: "Створити групу · 2 погоджених" }).click();
  const dialog = page.getByTestId("group-create-dialog");
  await expect(dialog.getByText("Погоджений графік", { exact: true })).toBeVisible();
  await dialog.getByLabel("Назва групи").fill(`Погоджена ${suffix}`);
  await dialog.getByRole("button", { name: "Створити групу і зарахувати" }).click();
  const schedule = page.getByRole("dialog", { name: "Додати заняття або розклад" });
  await expect(schedule).toBeVisible();
  await expect(schedule.getByLabel("Початок", { exact: true })).toHaveCount(2);
  await expect(schedule.getByLabel("Дата початку")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
