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
