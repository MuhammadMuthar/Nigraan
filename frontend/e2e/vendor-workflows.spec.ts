import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
  await page.waitForURL("**/run");
}

async function resetAndLoad(page: Page) {
  await page.getByRole("button", { name: "Reset data", exact: true }).click();
  await expect(page.getByText("No payment run this week yet")).toBeVisible();
  await page.getByRole("button", { name: "Load demo week", exact: true }).click();
  await expect(page.getByRole("region", { name: "Payment run summary" })).toBeVisible();
}

function pakistanIban(bank: string, account: string) {
  const base = `PK00${bank}${account}`;
  const digits = (base.slice(4) + base.slice(0, 4)).split("").map((char) => /[A-Z]/.test(char) ? String(parseInt(char, 36)) : char).join("");
  return `PK${String(BigInt(98) - BigInt(digits) % BigInt(97)).padStart(2, "0")}${bank}${account}`;
}

// A readable synthetic invoice exercises the real PDF reader without adding a fixture dependency.
function invoicePdf(vendor: string, number: string) {
  const lines = [vendor, `Invoice No: ${number}`, "Invoice Date: 10-10-2026", "Due Date: 13-10-2026", "Sub Total Rs 100.00", "Sales Tax @ 18% Rs 18.00", "Total Amount Rs 118.00"];
  const stream = `BT /F1 12 Tf 40 780 Td ${lines.map((line, index) => `${index ? "0 -25 Td " : ""}(${line.replace(/[()\\]/g, "\\$&")}) Tj`).join("\n")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return Buffer.from(pdf);
}

async function fillVendorDetails(page: Page, name?: string) {
  const dialog = page.getByRole("dialog");
  if (name) await dialog.getByRole("textbox", { name: "Vendor name", exact: true }).fill(name);
  await dialog.getByRole("textbox", { name: "Contact phone" }).fill("03000000001");
  await dialog.getByRole("textbox", { name: "Business address" }).fill("Synthetic workflow test address, Lahore");
  await dialog.getByRole("textbox", { name: "Bank name", exact: true }).fill("HBL");
  await dialog.getByRole("textbox", { name: "Pakistan IBAN", exact: true }).fill(pakistanIban("HABB", "1234567890123456"));
}

test("vendor creation and bank changes require an independent approver", async ({ page }) => {
  await signIn(page, "Haji Abdul Rashid");
  await resetAndLoad(page);
  await page.goto("/vendors");
  await page.getByRole("button", { name: "Add vendor", exact: true }).click();
  await fillVendorDetails(page, "Synthetic Quartz Workflow Supplies");
  await page.getByRole("dialog").getByRole("button", { name: "Create vendor", exact: true }).click();
  const vendorLink = page.getByRole("link", { name: "Synthetic Quartz Workflow Supplies", exact: true });
  await expect(vendorLink).toBeVisible();
  const vendorPath = await vendorLink.getAttribute("href");
  await page.getByRole("textbox", { name: "Search vendors" }).fill("Synthetic Quartz Workflow Supplies");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await vendorLink.click();
  await page.getByRole("button", { name: "Request bank change", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox", { name: "New bank name" }).fill("MCB");
  await dialog.getByRole("textbox", { name: "New Pakistan IBAN" }).fill("PK00INVALID");
  await dialog.getByRole("button", { name: "Submit bank change" }).click();
  await expect(dialog.getByRole("alert")).toContainText("IBAN");
  await dialog.getByRole("textbox", { name: "New Pakistan IBAN" }).fill(pakistanIban("MUCB", "9876543210987654"));
  await dialog.getByRole("button", { name: "Submit bank change" }).click();
  await expect(page.getByText("Pending approval", { exact: true })).toBeVisible();
  await expect(page.getByText("You requested this change.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve bank change", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "Bilal");
  await page.goto("/vendors");
  await expect(page.getByRole("button", { name: "Add vendor", exact: true })).toHaveCount(0);
  await page.goto(vendorPath!);
  await page.getByRole("button", { name: "Approve bank change", exact: true }).click();
  await expect(page.getByText("Pending approval", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Current account", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Previous account", { exact: true })).toHaveCount(1);
  await expect(page.getByText(/MCB ••7654/)).toBeVisible();
});

test("unmatched uploads recover through vendor creation or existing-vendor selection", async ({ page }) => {
  await signIn(page, "Haji Abdul Rashid");
  await resetAndLoad(page);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await signIn(page, "Sana Iqbal");
  await page.goto("/upload");
  const newName = "Unlisted Synthetic Zircon Document Supplier";
  await page.getByLabel("Invoice files", { exact: true }).setInputFiles({ name: "synthetic-unmatched.pdf", mimeType: "application/pdf", buffer: invoicePdf(newName, "WORKFLOW-900001") });
  await expect(page.getByText("No vendor matched.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm fields & score", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Add vendor", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("textbox", { name: "Vendor name", exact: true })).toHaveValue(newName);
  await fillVendorDetails(page);
  const created = page.waitForResponse((response) => response.url().endsWith("/vendors") && response.request().method() === "POST");
  await page.getByRole("dialog").getByRole("button", { name: "Create vendor", exact: true }).click();
  const vendorId = (await (await created).json()).id;
  await expect(page.getByRole("combobox", { name: "Match invoice to vendor" })).toHaveValue(String(vendorId));
  const scored = page.waitForResponse((response) => /\/invoices\/\d+\/score$/.test(response.url()));
  await page.getByRole("button", { name: "Confirm fields & score", exact: true }).click();
  expect((await scored).ok()).toBeTruthy();
  await expect(page.getByText("manually selected", { exact: true })).toBeVisible();

  await page.getByLabel("Invoice files", { exact: true }).setInputFiles({ name: "synthetic-existing-match.pdf", mimeType: "application/pdf", buffer: invoicePdf("Unlisted Synthetic Helium Wholesale", "WORKFLOW-900002") });
  const selector = page.getByRole("combobox", { name: "Match invoice to vendor" });
  await expect(selector).toBeVisible();
  await selector.selectOption(String(vendorId));
  const confirmed = page.waitForResponse((response) => /\/invoices\/\d+$/.test(response.url()) && response.request().method() === "PATCH");
  const rescored = page.waitForResponse((response) => /\/invoices\/\d+\/score$/.test(response.url()));
  await page.getByRole("button", { name: "Confirm fields & score", exact: true }).click();
  const confirmResponse = await confirmed;
  expect(confirmResponse.ok()).toBeTruthy();
  expect(confirmResponse.request().postDataJSON().vendor_id).toBe(vendorId);
  expect((await rescored).ok()).toBeTruthy();
  await expect(page.getByText("manually selected", { exact: true })).toHaveCount(2);
});
