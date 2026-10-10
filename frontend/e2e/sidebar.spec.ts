import { expect, test } from "@playwright/test";

test("sidebar minimizes left, preserves labelled links, and remembers its width", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Sana Iqbal/ }).click();
  await page.waitForURL("**/run");
  const sidebar = page.getByRole("complementary", { name: "Workspace sidebar" });
  const width = async () => Math.round((await sidebar.boundingBox())!.width);
  await expect.poll(width).toBe(256);
  const minimize = page.getByRole("button", { name: "Minimize sidebar", exact: true });
  await minimize.focus();
  await page.keyboard.press("Enter");
  await expect.poll(width).toBe(80);
  await expect(page.getByRole("button", { name: "Expand sidebar", exact: true })).toBeFocused();
  for (const name of ["Payment run", "Flagged invoices", "Cases", "Upload invoices", "Cash outlook", "Dashboard", "Vendors"]) {
    await expect(sidebar.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await sidebar.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page.getByText("Offline ML evaluation · synthetic hold-out", { exact: true })).toBeVisible();
  await page.reload();
  await expect.poll(width).toBe(80);
  await page.getByRole("button", { name: "Expand sidebar", exact: true }).click();
  await expect.poll(width).toBe(256);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: "Minimize sidebar", exact: true }).click();
  await expect.poll(width).toBe(80);
  const duration = await sidebar.evaluate((el) => getComputedStyle(el).transitionDuration);
  expect(duration.split(",").every((value) => parseFloat(value) < 0.01)).toBeTruthy();
});

test("mobile navigation closes towards the left and honors reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await page.getByRole("button", { name: /Sana Iqbal/ }).click();
  await page.waitForURL("**/run");
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  const navigation = page.getByRole("dialog", { name: "Workspace navigation" });
  await expect(navigation).toBeVisible();
  await expect.poll(async () => (await navigation.boundingBox())!.x).toBe(0);
  const animation = await navigation.evaluate((el) => getComputedStyle(el).animationName);
  expect(animation).toContain("sheet-in-left");
  await page.keyboard.press("Escape");
  await expect(navigation).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Open navigation", exact: true })).toBeFocused();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: "Open navigation", exact: true }).click();
  const duration = await navigation.evaluate((el) => getComputedStyle(el).animationDuration);
  expect(parseFloat(duration)).toBeLessThan(0.01);
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await expect(navigation).not.toBeVisible();
});
