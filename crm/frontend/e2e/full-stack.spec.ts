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
  await expect(page.getByText(/Test Child/).first()).toBeVisible();
  await expect(page.getByText(/Марта/)).toHaveCount(0);
});

test("mobile shell does not overflow horizontally", async ({ page }) => {
  await login(page);
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport + 2);
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
});

test("owner can open modular schedule workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Розклад", { exact: true }).first().click();
  await expect(page.getByTestId("schedule-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Додати заняття" })).toBeVisible();
});

test("owner can open modular attendance workspace", async ({ page }) => {
  await login(page);
  await page.getByText("Відвідування", { exact: true }).first().click();
  await expect(page.getByTestId("attendance-workspace")).toBeVisible();
});

test("owner can open modular staff locations and settings workspaces", async ({ page }) => {
  await login(page);

  await page.getByText("Працівники", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Працівники", level: 1 })).toBeVisible();

  await page.getByText("Локації", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Локації школи" })).toBeVisible();

  await page.getByText("Налаштування", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Основні налаштування" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Вигляд інтерфейсу" })).toBeVisible();

  await page.getByText("Звіти", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Заявка → учень" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Оплати" })).toBeVisible();
});
