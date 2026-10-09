import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await page.waitForURL("**/run");
}

test("payment run: load week, red lines locked, case evidence, owner releases green and confirms fraud", async ({ page }) => {
  await signIn(page, "Sana Iqbal");
  await page.getByRole("button", { name: "Reset data" }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();

  await page.getByRole("button", { name: "Load demo week" }).click();
  await expect(page.getByText("Cash impact of this run")).toBeVisible();
  await expect(page.getByText("If every line were released")).toBeVisible();

  // red lines: Release is disabled and a case link exists
  const blockedRow = page.locator("tbody tr", { has: page.getByText("Blocked", { exact: true }) }).first();
  await expect(blockedRow.getByRole("button", { name: "Release" })).toBeDisabled();
  // accountant cannot approve
  await expect(page.getByRole("button", { name: /Approve all green/ })).toBeDisabled();

  // open the line drawer: agent trace is shown
  await blockedRow.click();
  await expect(page.getByText("Agent trace").first()).toBeVisible();
  await page.keyboard.press("Escape");

  await blockedRow.getByRole("link", { name: "View case" }).click();
  await expect(page.getByText("Why Nigraan stopped this payment")).toBeVisible();
  await expect(page.getByText("Suggested verification")).toBeVisible();

  // owner: approve all green, then confirm fraud on a case
  await page.getByRole("button", { name: "Sign out" }).click();
  await signIn(page, "Haji Abdul Rashid");
  await page.getByRole("button", { name: /Approve all green/ }).click();
  await expect(page.getByText(/Approved \d+ green line/)).toBeVisible();

  await page.locator("tbody tr", { has: page.getByText("Blocked", { exact: true }) }).first().getByRole("link", { name: "View case" }).click();
  await page.getByRole("button", { name: "Confirm fraud" }).click();
  await page.getByPlaceholder(/What did you verify/).fill("Called vendor on registered number; they never sent this invoice.");
  await page.getByRole("button", { name: "Save outcome" }).click();
  await expect(page.getByText("Confirmed fraud").first()).toBeVisible();

  await page.goto("/dashboard");
  await expect(page.getByText("Rupees protected this month")).toBeVisible();
  await expect(page.getByText("Fraud firewall vs rules-only baseline")).toBeVisible();
});
