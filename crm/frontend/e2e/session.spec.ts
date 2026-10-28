import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Email").fill("owner@smoke.test");
  await page.getByLabel("Пароль").fill("smoke-test-password-123");
  await page.getByRole("button", { name: "Увійти", exact: true }).click();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
}

test("expired session immediately shows login when returning to the tab", async ({ page }) => {
  await login(page);
  const expiresAt = await page.evaluate(() => {
    const session = JSON.parse(sessionStorage.getItem("school-crm-session")!);
    return JSON.parse(atob(session.accessToken.split(".")[1])).exp * 1000;
  });
  await page.clock.install();
  await page.clock.setSystemTime(expiresAt + 1000);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Увійдіть у CRM" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Сесія завершилася");
  expect(await page.evaluate(() => sessionStorage.getItem("school-crm-session"))).toBeNull();
});

test("authenticated 401 displays login instead of leaving editable CRM open", async ({ page }) => {
  await login(page);
  await page.route("**/api/workspace/students/page**", route => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Invalid token" }) }));
  await page.getByText("Учні", { exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Увійдіть у CRM" })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Сесія завершилася");
});

test("temporary server failure does not discard the saved login", async ({ page }) => {
  await login(page);
  await page.route("**/api/auth/me", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Service unavailable" }) }));
  await page.reload();
  await expect(page.getByText("Дашборд", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Увійдіть у CRM" })).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem("school-crm-session"))).not.toBeNull();
});
