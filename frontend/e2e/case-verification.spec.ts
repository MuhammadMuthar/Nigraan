import { expect, test } from "@playwright/test";

test("case resolution requires recorded verification and preserves the form after a service failure", async ({ page, request }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Haji Abdul Rashid/ }).click();
  await page.waitForURL("**/run");
  await page.getByRole("button", { name: "Reset data", exact: true }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();
  await page.getByRole("button", { name: "Load demo week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Payment run summary" })).toBeVisible();
  await page.goto("/flagged");
  await page.locator("tbody tr", { has: page.getByText("Blocked", { exact: true }) }).first().getByRole("link", { name: "View case" }).click();
  await page.waitForURL(/\/cases\/\d+$/);
  const caseId = page.url().split("/").pop();
  const token = await page.evaluate(() => localStorage.getItem("nigraan.token"));
  const noVerification = await request.post(`http://localhost:8000/api/v1/cases/${caseId}/resolve`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { outcome: "false_alarm", note: "A substantive note alone is not verification", block_vendor: false },
  });
  expect(noVerification.status()).toBe(422);

  await expect(page.getByText("Current registered phone", { exact: true })).toBeVisible();
  await expect(page.getByText("Checks required for the outcome", { exact: true })).toBeVisible();
  const script = page.locator('p[aria-live="polite"]');
  const englishScript = await script.innerText();
  await page.getByRole("button", { name: "Call script in Roman Urdu", exact: true }).click();
  await expect(script).not.toHaveText(englishScript);
  await page.getByRole("button", { name: "Call script in English", exact: true }).click();
  await expect(script).toHaveText(englishScript);

  await page.getByRole("button", { name: "False alarm", exact: true }).click();
  const dialog = page.getByRole("dialog");
  const save = dialog.getByRole("button", { name: "Save outcome", exact: true });
  await expect(save).toBeDisabled();
  await dialog.getByLabel("Verification note", { exact: true }).fill("Synthetic fixture documents establish a legitimate second delivery.");
  await expect(save).toBeDisabled();
  await dialog.getByLabel("Evidence reference", { exact: true }).fill("Demo fixture: second delivery receipt and invoice history.");
  await dialog.getByLabel("Verification method", { exact: true }).selectOption("documents");
  await expect(save).toBeDisabled();
  const checks = dialog.getByRole("group", { name: "Required verification checks" }).getByRole("checkbox");
  expect(await checks.count()).toBeGreaterThan(0);
  for (const check of await checks.all()) await check.check();
  await expect(save).toBeEnabled();

  let unavailable = true;
  await page.route(`**/api/v1/cases/${caseId}/resolve`, async (route) => {
    if (unavailable) await route.fulfill({ status: 503, json: { code: "unavailable", message: "Verification service temporarily unavailable." } });
    else await route.continue();
  });
  await save.click();
  await expect(dialog.getByRole("alert")).toContainText("Verification service temporarily unavailable.");
  await expect(dialog.getByLabel("Evidence reference", { exact: true })).toHaveValue("Demo fixture: second delivery receipt and invoice history.");
  unavailable = false;
  await save.click();
  await expect(dialog).not.toBeVisible();
  const recorded = page.getByRole("region", { name: "Recorded verification" });
  await expect(recorded).toContainText("Legitimate payment verified");
  await expect(recorded).toContainText("Haji Abdul Rashid");
  await expect(recorded).toContainText("Demo fixture: second delivery receipt and invoice history.");
});
