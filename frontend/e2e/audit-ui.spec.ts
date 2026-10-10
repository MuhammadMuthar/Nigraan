import { expect, test } from "@playwright/test";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByRole("button", { name: /Haji Abdul Rashid/ }).click();
  await page.waitForURL("**/run");
}

test("cases show a recoverable service error rather than an empty list", async ({ page }) => {
  await signIn(page);
  let unavailable = true;
  await page.route("**/api/v1/cases?source=auto", async (route) => {
    if (unavailable) await route.fulfill({ status: 503, json: { code: "unavailable", message: "Cases service temporarily unavailable." } });
    else await route.continue();
  });
  await page.goto("/cases");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Cases unavailable");
  await expect(page.getByText("No cases here", { exact: true })).not.toBeVisible();
  unavailable = false;
  await page.getByRole("button", { name: "Retry cases" }).click();
  await expect(page.getByRole("main").getByRole("alert")).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Retry cases" })).not.toBeVisible();
});

test("invoice details recover from a failed fetch and ignore a closed request", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Reset data", exact: true }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();
  await page.getByRole("button", { name: "Load demo week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Payment run summary" })).toBeVisible();
  await page.goto("/flagged?view=all");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  let unavailable = true;
  await page.route("**/api/v1/payments/*/score", async (route) => {
    if (unavailable) await route.fulfill({ status: 503, json: { code: "unavailable", message: "Score service temporarily unavailable." } });
    else await route.continue();
  });
  await page.locator("tbody tr").first().click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Score service temporarily unavailable.");
  unavailable = false;
  await page.getByRole("button", { name: "Retry invoice details" }).click();
  await expect(page.getByRole("dialog").getByText("Agent trace", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();

  // A late response from a drawer that was closed must not replace the next invoice.
  const rows = page.locator("tbody tr");
  const payee = await rows.nth(2).locator("td").nth(2).innerText();
  let releaseFirst!: () => void;
  const firstPending = new Promise<void>((resolve) => { releaseFirst = resolve; });
  let requests = 0;
  let heldUrl = "";
  await page.unroute("**/api/v1/payments/*/score");
  await page.route("**/api/v1/payments/*/score", async (route) => {
    requests += 1;
    if (requests === 1) {
      heldUrl = route.request().url();
      await firstPending;
    }
    await route.continue();
  });
  // Use an uncached invoice: reopening the first one correctly renders its cached result immediately.
  await rows.nth(1).click();
  await expect(page.getByRole("dialog").getByRole("status")).toBeVisible();
  await page.keyboard.press("Escape");
  await rows.nth(2).click();
  await expect(page.getByRole("dialog").getByText("Agent trace", { exact: true })).toBeVisible();
  const lateResponse = page.waitForResponse((response) => response.url() === heldUrl);
  releaseFirst();
  await lateResponse;
  await expect(page.getByRole("dialog")).toContainText(payee.trim().split("\n")[0]);
});

test("cash chart selects the clicked week and keeps negative balances signed", async ({ page }) => {
  await signIn(page);
  // A negative balance fixture exercises formatting independently of the demo's positive reserve.
  await page.route("**/api/v1/cash/projection", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.projection.weeks[2].closing = -1_234_500;
    body.projection.weeks[2].low = -2_000_000;
    await route.fulfill({ response, json: body });
  });
  await page.goto("/cash");
  await page.getByRole("button", { name: /^Week 1,/ }).click();
  const chart = page.locator(".recharts-wrapper").first();
  await chart.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
  const chartBox = await chart.boundingBox();
  const weekTick = await chart.locator("text").filter({ hasText: /^W3/ }).boundingBox();
  expect(chartBox).not.toBeNull();
  expect(weekTick).not.toBeNull();
  await page.mouse.move(weekTick!.x + weekTick!.width / 2, chartBox!.y + 120);
  await expect(chart.locator(".recharts-tooltip-wrapper")).toContainText("-Rs 12,345");
  await page.mouse.click(weekTick!.x + weekTick!.width / 2, chartBox!.y + 120);
  await expect(page.getByRole("heading", { name: "Week 3, day by day" })).toBeVisible();
  await page.getByRole("button", { name: /^Week 2,/ }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Week 2, day by day" })).toBeVisible();
});

test("dashboard recovers from errors and renders the measured review study", async ({ page }) => {
  await signIn(page);
  let unavailable = true;
  await page.route("**/api/v1/dashboard/summary", async (route) => {
    if (unavailable) await route.fulfill({ status: 503, json: { code: "unavailable", message: "Evaluation service temporarily unavailable." } });
    else await route.continue();
  });
  await page.goto("/dashboard");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Evaluation service temporarily unavailable.");
  unavailable = false;
  const summary = page.waitForResponse((response) => response.url().endsWith("/dashboard/summary") && response.ok());
  await page.getByRole("button", { name: "Retry dashboard", exact: true }).click();
  const data = await (await summary).json();
  const study = data.metrics.review;
  expect(study.n_payments).toBe(data.metrics.fraud.n_payments);
  const region = page.getByRole("region", { name: "Review evaluation" });
  await expect(region.getByRole("heading", { name: "Expert rules comparison", exact: true })).toBeVisible();
  const expert = region.getByRole("row", { name: /Expert rules/ });
  await expect(expert).toContainText(`${(study.rules_comparison.expert.recall * 100).toFixed(1)}%`);
  await expect(expert).toContainText(`${(study.rules_comparison.expert.false_alarm_rate * 100).toFixed(1)}%`);
  await expect(region.getByRole("heading", { name: "Without the invoice-age feature", exact: true })).toBeVisible();
  await expect(page.getByText("weekly receipt error for the current conservative policy", { exact: true })).toBeVisible();
});
