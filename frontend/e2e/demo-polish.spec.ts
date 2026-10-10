import { expect, test } from "@playwright/test";

// These flows supplement the existing payment/approval happy path using real API data.
test("mobile navigation preserves accountant permissions and exposes every route", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  await page.getByRole("button", { name: /Sana Iqbal/ }).click();
  await page.waitForURL("**/run");
  await expect(page.getByRole("button", { name: "Retrain", exact: true })).toBeDisabled();
  const approve = page.getByRole("button", { name: /Approve all green/ });
  if (await approve.count()) await expect(approve).toBeDisabled();
  await page.getByRole("button", { name: "Open navigation" }).click();
  const nav = page.getByRole("dialog");
  for (const name of ["Payment run", "Cases", "Upload invoices", "Cash outlook", "Dashboard", "Vendors"]) {
    await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await nav.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(nav).not.toBeVisible();
  await expect(page.getByText("Rupees protected this month")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("dialog").getByRole("link", { name: "Upload invoices", exact: true }).click();
  await expect(page.getByRole("button", { name: /resent invoice/ }).first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.getByRole("button", { name: "Open user menu" }).click();
  await expect(page.getByText("Signed in as Accountant.", { exact: false })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.waitForURL("**/login");
});

test("demo evidence tabs, Roman Urdu, upload confidence, and cash scenario remain functional", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Haji Abdul Rashid/ }).click();
  await page.waitForURL("**/run");
  await page.getByRole("button", { name: "Reset data", exact: true }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();
  await page.getByRole("button", { name: "Load demo week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Payment run summary" })).toBeVisible();
  await page.locator("tbody tr", { has: page.getByText("Blocked", { exact: true }) }).first().getByRole("link", { name: "View case" }).click();
  await expect(page.getByRole("heading", { name: "Suggested verification" })).toBeVisible();
  for (const name of ["Duplicate", "Bank history", "Relationships", "Invoice"]) {
    const tab = page.getByRole("tab", { name, exact: true });
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
  }
  await page.getByRole("button", { name: "Roman Urdu", exact: true }).click();
  await expect(page.getByRole("button", { name: "English", exact: true })).toBeVisible();
  await page.goto("/upload");
  await expect(page.getByRole("button", { name: "Choose invoice files" })).toBeVisible();
  await page.getByRole("button", { name: /resent invoice/ }).first().click();
  await expect(page.getByText("Extracted fields", { exact: true })).toBeVisible();
  await expect(page.getByText("Confidence", { exact: true })).toBeVisible();
  await expect(page.getByText("Blocked", { exact: true })).toBeVisible();
  await page.goto("/cash");
  await expect(page.getByRole("heading", { name: "13-week cash projection" })).toBeVisible();
  const week = page.getByRole("button", { name: /^Week 2,/ });
  await week.click();
  await expect(page.getByRole("heading", { name: "Week 2, day by day" })).toBeVisible();
  await page.getByRole("button", { name: "Move", exact: true }).first().click();
  await expect(page.getByRole("textbox", { name: /New collection date/ })).toBeVisible();
  const response = page.waitForResponse((r) => r.url().endsWith("/cash/scenarios") && r.request().method() === "POST");
  await page.getByRole("button", { name: "Run scenario", exact: true }).click();
  expect((await response).ok()).toBeTruthy();
  await expect(page.getByText("Low point change", { exact: true })).toBeVisible();
  await page.goto("/dashboard");
  await expect(page.getByText("Offline ML evaluation · synthetic hold-out", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open payment run", exact: true })).toBeVisible();
});
