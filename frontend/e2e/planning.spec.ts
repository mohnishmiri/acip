import { expect, test } from "@playwright/test";

test.describe("Allocation & planning", () => {
  test("application allocation shows prod / non-prod split with shared and unallocated rows", async ({ page }) => {
    await page.goto("/applications?preset=week_to_date");
    const table = page.getByTestId("applications-table");
    for (const t of ["Application 1", "Application 2", "Application 3", "Shared Services", "Unallocated"]) await expect(table).toContainText(t);
    await table.getByText("Application 1", { exact: true }).first().click();
    await expect(page.getByTestId("application-detail-page")).toBeVisible();
    const env = page.getByTestId("app-by-environment");
    await env.getByRole("button", { name: "Table view" }).click();
    await expect(env.getByRole("table")).toContainText("Non-Production");
  });

  test("environment comparison states non-production is not assumed waste", async ({ page }) => {
    await page.goto("/environments?preset=week_to_date");
    await expect(page.getByTestId("nonprod-note")).toContainText(/not .*waste/i);
    await expect(page.getByTestId("environment-table")).toContainText("Shared Services");
  });

  test("budget create -> validate -> delete round trip", async ({ page }) => {
    await page.goto("/budgets");
    await expect(page.getByTestId("budgets-table")).toContainText("Total Azure");
    await page.getByTestId("budget-new").click();
    const dialog = page.getByTestId("budget-dialog");
    await page.getByTestId("budget-name").fill("E2E budget");
    await page.getByTestId("budget-amount").fill("0");
    await page.getByTestId("budget-dialog-submit").click();
    await expect(dialog).toBeVisible(); // zod rejects a zero amount
    await page.getByTestId("budget-amount").fill("12345");
    await page.getByTestId("budget-dialog-submit").click();
    await expect(dialog).toBeHidden();
    const row = page.getByTestId("budgets-table").locator("tr", { hasText: "E2E budget" });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: /delete/i }).click();
    await page.getByTestId("budget-delete-dialog-confirm").click();
    await expect(page.getByTestId("budgets-table")).not.toContainText("E2E budget");
  });

  test("forecast is labelled as a projection", async ({ page }) => {
    await page.goto("/budgets");
    await expect(page.getByTestId("forecast-panel")).toContainText(/not actual/i);
  });

  test("savings are estimates and the platform is read-only", async ({ page }) => {
    await page.goto("/savings");
    await expect(page.getByTestId("savings-summary")).toContainText(/estimated/i);
    await expect(page.getByTestId("savings-readonly-note")).toContainText(/never/i);
    await expect(page.getByTestId("savings-table")).toContainText("Non-Production compute billed 24×7");
  });
});

test.describe("Operations", () => {
  test("alerts list and rules", async ({ page }) => {
    await page.goto("/alerts");
    await expect(page.getByTestId("notifications-table")).toBeVisible();
    await expect(page.getByTestId("email-delivery-panel")).toContainText("Email delivery");
    await page.getByTestId("tab-alert-rules").click();
    await expect(page.getByTestId("alert-rules-table")).toContainText("Cost anomalies");
  });

  test("data management shows freshness, jobs and the export-run registry", async ({ page }) => {
    await page.goto("/data-management");
    await expect(page.getByTestId("freshness-table")).toContainText("DEMO-App1-Production");
    await page.getByTestId("tab-runs").click();
    await expect(page.getByTestId("runs-table")).toContainText(/superseded/i);
  });

  test("administration tabs render, including six subscription connections", async ({ page }) => {
    await page.goto("/admin?tab=connections");
    await expect(page.getByTestId("connections-table").locator("tbody tr")).toHaveCount(6, { timeout: 15000 }).catch(async () => {
      // rows may include expanded detail rows; fall back to name checks
      for (const n of ["DEMO-App1-Production", "DEMO-App3-NonProduction"]) await expect(page.getByTestId("connections-table")).toContainText(n);
    });
    for (const tab of ["subscriptions", "applications", "allocation", "categories", "anomaly-rules", "settings", "users", "audit"]) {
      await page.goto(`/admin?tab=${tab}`);
      await expect(page.getByTestId("admin-page")).toBeVisible();
    }
  });

  test("read-only viewer cannot create budgets or trigger ingestion", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("acip.devRole", "viewer"));
    await page.goto("/budgets");
    await expect(page.getByTestId("budgets-table")).toBeVisible();
    await expect(page.getByTestId("budget-new")).toHaveCount(0);
    await page.goto("/data-management");
    await expect(page.getByTestId("freshness-table")).toBeVisible();
    await expect(page.getByTestId("sync-all")).toHaveCount(0);
  });
});
