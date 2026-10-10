import { expect, test } from "@playwright/test";

test("live rule comparisons remain visible and combined vendor exposure needs owner approval", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Haji Abdul Rashid/ }).click();
  await page.waitForURL("**/run");
  await page.getByRole("button", { name: "Reset data", exact: true }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();
  await page.getByRole("button", { name: "Load demo week", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Compare this run with rule checks" })).toBeVisible();
  await expect(page.getByText("Current payment lines, not an accuracy test.", { exact: false })).toBeVisible();

  const token = await page.evaluate(() => localStorage.getItem("nigraan.token"));
  const runResponse = await page.request.get("http://localhost:8000/api/v1/payment-runs/current", { headers: { Authorization: `Bearer ${token}` } });
  expect(runResponse.ok()).toBeTruthy();
  let { run } = await runResponse.json();
  // The shipped demo already blocks the split lines. Record counterfactual synthetic
  // verification outcomes to exercise controls after recovery, without changing scores.
  const candidates = run.lines.filter((item: { vendor: string; status: string; amount: number; case: { status: string } }) => item.vendor === "Ravi Goods Transport" && item.status === "blocked" && item.amount <= run.approval_limit && item.case.status === "open");
  expect(candidates.length).toBeGreaterThan(1);
  expect(candidates.reduce((sum: number, item: { amount: number }) => sum + item.amount, 0)).toBeGreaterThan(run.approval_limit);
  const headers = { Authorization: `Bearer ${token}` };
  for (const candidate of candidates) {
    const detail = await (await page.request.get(`http://localhost:8000/api/v1/cases/${candidate.case.id}`, { headers })).json();
    const resolved = await page.request.post(`http://localhost:8000/api/v1/cases/${candidate.case.id}/resolve`, { headers, data: {
      outcome: "false_alarm", note: "Counterfactual synthetic control test: invoices independently verified for recovery.",
      verification: { result: "verified_legitimate", method: "documents", reference: "Synthetic test purchase records and vendor confirmation, not a real verification.", checks: detail.verification_plan.checklist.map((check: { id: string }) => check.id) },
    } });
    expect(resolved.ok()).toBeTruthy();
  }
  ({ run } = await (await page.request.get("http://localhost:8000/api/v1/payment-runs/current", { headers })).json());
  const line = run.lines.find((item: { requires_owner_approval: boolean; status: string; amount: number; decision: string }) => item.requires_owner_approval && item.status === "pending" && item.amount <= run.approval_limit && item.decision === "review");
  expect(line).toBeTruthy();
  const usersResponse = await page.request.get("http://localhost:8000/api/v1/auth/demo-users");
  const users = await usersResponse.json();
  const approver = users.find((user: { role: string }) => user.role === "approver");
  expect(approver).toBeTruthy();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(approver.name) }).click();
  await page.waitForURL("**/run");
  await expect(page.getByRole("button", { name: "Reset data", exact: true })).toHaveCount(0);
  await expect(page.getByText("Only the owner can reset data", { exact: true })).toBeVisible();
  await page.goto("/flagged?view=all");
  const row = page.getByRole("row").filter({ has: page.getByRole("button", { name: `Inspect ${line.vendor}, invoice ${line.invoice_no}`, exact: true }) });
  await expect(row).toContainText(`Simple: ${line.rules_comparison.simple.flagged ? "flag" : "no flag"}`);
  await expect(row).toContainText(`Expert: ${line.rules_comparison.expert.flagged ? "flag" : "no flag"}`);
  await row.getByRole("button", { name: "Second approval", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText("combined run commitment");
  await expect(page.getByRole("button", { name: "Approve as second approver", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Hold", exact: true })).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();

  await row.getByRole("button", { name: `Inspect ${line.vendor}, invoice ${line.invoice_no}`, exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("heading", { name: "Rule-check comparison" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("XGBoost and the anomaly detector learn from payment history");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});
