// Stage 3 regression: paginated registries must remain stable on desktop and mobile.
import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await expect(page.getByTestId("crm-config-error")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Увійдіть у CRM" })).toBeVisible();
  await page.getByLabel("Email").fill("owner@smoke.test");
  await page.getByLabel("Пароль").fill("smoke-test-password-123");
  await page.getByRole("button", { name: "Увійти" }).click();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
}

test("owner can sign in and see the real smoke lead", async ({ page }) => {
  await login(page);
  await page.getByText("Заявки", { exact: true }).first().click();
  const smokeLead = page.getByText(/Test Child/).first();
  await expect(smokeLead).toBeVisible();
  await expect(page.getByText(/Марта/)).toHaveCount(0);
  await smokeLead.click();
  await expect(page.getByTestId("lead-drawer")).toBeVisible();
  await page.getByTestId("lead-drawer").getByRole("button", { name: "Закрити картку заявки" }).click();
  await expect(page.getByTestId("lead-drawer")).toHaveCount(0);
});

test("moving a lead to waiting does not start enrollment", async ({ page }) => {
  await login(page);

  const uniqueSuffix = Array.from({ length: 8 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");
  const childName = `Waitlist ${uniqueSuffix}`;
  const childPhone = `+38067${Math.floor(1_000_000 + Math.random() * 9_000_000)}`;
  const intake = await page.evaluate(async ({ childName, childPhone }) => {
    const session = JSON.parse(sessionStorage.getItem("school-crm-session") ?? "null");
    const response = await fetch("/api/intake", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        "X-Organization-Id": session.organizationId,
      },
      body: JSON.stringify({
        child_first_name: childName,
        child_age: 9,
        contact_name: "Тестова мама",
        phone: childPhone,
        source: "phone",
      }),
    });
    return { status: response.status };
  }, { childName, childPhone });
  expect(intake.status).toBe(201);

  await page.reload();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
  await page.getByText("Заявки", { exact: true }).first().click();

  const newColumn = page.locator(".kanbanColumn.column-new");
  const waitingColumn = page.locator(".kanbanColumn.column-waiting");
  const card = newColumn.locator(".leadKanbanCard").filter({ hasText: childName });
  await expect(card).toBeVisible();
  const isMobile = (page.viewportSize()?.width ?? 1280) <= 500;

  const transitionResponse = page.waitForResponse((response) =>
    response.url().includes("/crm-status") && response.request().method() === "PATCH"
  );
  if (isMobile) {
    await card.click();
    await page.locator(".mobileLeadMoreAction").click();
    await page.getByRole("button", { name: "Перемістити заявку" }).click();
    await page.locator(".mobileLeadStageList").getByRole("button", { name: /Очікує групу/ }).click();
  } else {
    await card.dragTo(waitingColumn);
  }
  expect((await transitionResponse).ok()).toBeTruthy();
  const waitingCard = waitingColumn.locator(".leadKanbanCard").filter({ hasText: childName });
  await expect(waitingCard).toBeVisible();
  await expect(page.getByTestId("lead-enrollment-workflow")).toHaveCount(0);

  if (!isMobile) {
    await expect(page.getByTestId("lead-drawer")).toHaveCount(0);
    await waitingCard.click();
    await page.setViewportSize({ width: 390, height: 844 });
  }
  await expect(page.getByTestId("lead-drawer")).toBeVisible();
  await page.locator(".mobileLeadPrimaryAction").click();
  await expect(page.getByTestId("lead-enrollment-workflow")).toBeVisible();
});

test("a scheduled trial date and time can be edited from the lead card", async ({ page }) => {
  await login(page);

  const suffix = Array.from({ length: 8 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");
  const childName = "Editable Trial " + suffix;
  const childPhone = "+38067" + String(Math.floor(1_000_000 + Math.random() * 9_000_000));
  const setup = await page.evaluate(async ({ childName, childPhone }) => {
    const session = JSON.parse(sessionStorage.getItem("school-crm-session") ?? "null");
    const headers = {
      "Content-Type": "application/json",
      Authorization: "Bearer " + session.accessToken,
      "X-Organization-Id": session.organizationId,
    };
    const intakeResponse = await fetch("/api/intake", {
      method: "POST",
      headers,
      body: JSON.stringify({
        child_first_name: childName,
        child_age: 9,
        contact_name: "Тестова мама",
        phone: childPhone,
        source: "phone",
      }),
    });
    const intake = await intakeResponse.json();
    if (!intakeResponse.ok) return { status: intakeResponse.status };
    const starts = new Date();
    starts.setDate(starts.getDate() + 3);
    starts.setHours(17, 0, 0, 0);
    const trialResponse = await fetch("/api/trial-lessons", {
      method: "POST",
      headers,
      body: JSON.stringify({ student_id: intake.student_id, location_id: null, starts_at: starts.toISOString() }),
    });
    return { status: trialResponse.status };
  }, { childName, childPhone });
  expect(setup.status).toBe(201);

  await page.reload();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
  await page.getByText("Заявки", { exact: true }).first().click();
  const trialCard = page.locator(".kanbanColumn.column-trial .leadKanbanCard").filter({ hasText: childName });
  await expect(trialCard).toBeVisible();
  await trialCard.click();

  const drawer = page.getByTestId("lead-drawer");
  await drawer.getByRole("button", { name: "Змінити дату, час і локацію пробного" }).click();
  const time = drawer.getByLabel("Час");
  await expect(time).toBeVisible();
  await time.selectOption("18:00");

  const update = page.waitForResponse((response) =>
    response.url().includes("/trial-lessons/")
      && !response.url().includes("/complete")
      && response.request().method() === "PATCH"
  );
  await drawer.getByRole("button", { name: "Підтвердити пробне" }).click();
  expect((await update).ok()).toBeTruthy();
  await expect(drawer.locator(".trialSummary")).toContainText("18:00");
});

test("mobile shell does not overflow horizontally", async ({ page }) => {
  await login(page);
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 2);
});


test("owner can open extracted CRM creation dialogs", async ({ page }) => {
  await login(page);

  await page.getByRole("button", { name: "Нова заявка" }).click();
  await expect(page.getByTestId("lead-create-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрити нову заявку" }).click();
  await expect(page.getByTestId("lead-create-dialog")).toHaveCount(0);

  await page.getByText("Працівники", { exact: true }).first().click();
  await page.getByRole("button", { name: "+ Працівник" }).click();
  await expect(page.getByTestId("staff-create-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрити нового працівника" }).click();

  await page.getByRole("button", { name: "Запросити в CRM" }).click();
  await expect(page.getByTestId("invite-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрити запрошення" }).click();

  await page.getByText("Локації", { exact: true }).first().click();
  await page.getByRole("button", { name: "+ Додати локацію" }).click();
  await expect(page.getByTestId("location-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрити локацію" }).click();

  await page.locator(".appNav").getByRole("button", { name: "Групи" }).click();
  await expect(page.getByTestId("groups-workspace")).toBeVisible();
  const groupsWorkspace = page.getByTestId("groups-workspace");
  const createGroupButton = groupsWorkspace.getByRole("button", { name: /\+ (Нова|Створити) групу/ }).first();
  if (await createGroupButton.isVisible()) {
    await createGroupButton.click();
  } else {
    await groupsWorkspace.getByRole("button", { name: "Створити порожню групу" }).click();
  }
  await expect(page.getByTestId("group-create-dialog")).toBeVisible();
  await page.getByRole("button", { name: "Закрити створення групи" }).click();
});

test("owner can open modular students workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Учні", { exact: true }).first().click();
  await expect(page.getByTestId("students-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Активні учні" })).toBeVisible();
});

test("owner can open modular groups workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Групи", { exact: true }).first().click();
  await expect(page.getByTestId("groups-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Активні групи" })).toBeVisible();
  const groupCards = page.locator(".groupCardButton");
  await expect(page.getByText("Завантаження груп…", { exact: true })).toHaveCount(0);
  if (await groupCards.count() === 0) {
    await page.getByRole("button", { name: "+ Нова група" }).click();
    await expect(page.getByRole("heading", { name: "Створити групу" })).toBeVisible();
    await page.getByLabel("Назва групи").fill(`Smoke Group ${Date.now()}`);
    await page.getByRole("button", { name: "Створити групу", exact: true }).click();
    await expect(page.getByTestId("group-create-dialog")).toHaveCount(0);
    await expect(groupCards.first()).toBeVisible();
  }
  await groupCards.first().click();
  await expect(page.getByTestId("group-detail-drawer")).toBeVisible();
  await page.getByTestId("group-detail-drawer").getByRole("button", { name: "Закрити групу" }).click();
  await expect(page.getByTestId("group-detail-drawer")).toHaveCount(0);
});

test("owner can open modular schedule workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Розклад", { exact: true }).first().click();
  await expect(page.getByTestId("schedule-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Додати заняття" })).toBeVisible();
  const currentDate = await page.evaluate(() => {
    const now = new Date();
    return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
  });
  await expect(page.getByLabel("Дата і час: дата", { exact: true })).toHaveValue(currentDate);
});

test("owner can open modular attendance workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Відвідування", { exact: true }).first().click();
  await expect(page.getByTestId("attendance-workspace")).toBeVisible();
});

test("owner can open modular payments workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Оплати", { exact: true }).first().click();
  await expect(page.getByTestId("payments-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Оплати учнів" })).toBeVisible();

  await page.getByRole("button", { name: "+ Тариф" }).click();
  await expect(page.getByTestId("plan-dialog")).toBeVisible();
  await page.getByTestId("plan-dialog").getByRole("button", { name: "×" }).click();
  await expect(page.getByTestId("plan-dialog")).toHaveCount(0);

  await page.getByRole("button", { name: "+ Нарахування" }).click();
  await expect(page.getByTestId("payment-create-dialog")).toBeVisible();
  await page.getByTestId("payment-create-dialog").getByRole("button", { name: "×" }).click();
  await expect(page.getByTestId("payment-create-dialog")).toHaveCount(0);
});

test("owner can open modular staff locations and settings workspaces", async ({ page }) => {
  await login(page);

  await page.getByText("Працівники", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Працівники", level: 1 })).toBeVisible();
  await page.locator(".staffButton").first().click();
  await expect(page.getByTestId("staff-drawer")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Обов’язки" })).toBeVisible();
  await page.getByTestId("staff-drawer").getByRole("button", { name: "×" }).click();
  await expect(page.getByTestId("staff-drawer")).toHaveCount(0);

  await page.getByText("Локації", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Локації школи" })).toBeVisible();

  await page.getByText("Налаштування", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Основні налаштування" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Вигляд інтерфейсу" })).toBeVisible();

  await page.getByText("Звіти", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Заявка → учень" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Оплати" })).toBeVisible();
});


test("student and group registries use database-backed page search", async ({ page }) => {
  await login(page);

  await page.getByText("Учні", { exact: true }).first().click();
  await expect(page.getByTestId("students-workspace")).toBeVisible();
  const studentRequest = page.waitForResponse((response) =>
    response.url().includes("/workspace/students/page") && response.request().method() === "GET"
  );
  await page.getByTestId("students-workspace").locator(".registrySearch input").fill("definitely-no-student");
  expect((await studentRequest).ok()).toBeTruthy();
  await expect(page.getByTestId("students-workspace").getByText("За цим фільтром учнів немає.")).toBeVisible();

  await page.getByText("Групи", { exact: true }).first().click();
  await expect(page.getByTestId("groups-workspace")).toBeVisible();
  const groupRequest = page.waitForResponse((response) =>
    response.url().includes("/workspace/groups/page") && response.request().method() === "GET"
  );
  await page.getByTestId("groups-workspace").locator(".registrySearch input").fill("definitely-no-group");
  expect((await groupRequest).ok()).toBeTruthy();
  await expect(page.getByTestId("groups-workspace").getByText("За пошуком груп не знайдено")).toBeVisible();

  const paymentPageRequest = page.waitForResponse((response) =>
    response.url().includes("/payments/page") && response.request().method() === "GET"
  );
  await page.getByText("Оплати", { exact: true }).first().click();
  expect((await paymentPageRequest).ok()).toBeTruthy();
  const paymentSearchRequest = page.waitForResponse((response) =>
    response.url().includes("/payments/page")
      && new URL(response.url()).searchParams.get("q") === "definitely-no-payment"
  );
  await page.getByTestId("payments-search").fill("definitely-no-payment");
  expect((await paymentSearchRequest).ok()).toBeTruthy();
  await expect(page.getByTestId("payments-workspace").getByText("За цим фільтром оплат не знайдено.")).toBeVisible();
});
