import { expect, test } from "@playwright/test";

test.describe("Cost Comparison", () => {
  test("weekly waterfall reconciles and drills to meter level with billing records", async ({ page }) => {
    await page.goto("/comparison?preset=week_to_date");
    await expect(page.getByTestId("cmp-previous")).toContainText("$100,000.00");
    await expect(page.getByTestId("cmp-current")).toContainText("$110,000.00");
    await expect(page.getByTestId("cmp-diff")).toContainText("$10,000.00");
    await expect(page.getByTestId("cmp-pct")).toContainText("10.0%");
    await expect(page.getByTestId("comparison-reconciliation")).toContainText(/reconciled exactly/i);
    const grid = page.getByTestId("contribution-grid");
    await grid.getByText("Azure SQL", { exact: true }).first().click();
    await expect(page.getByTestId("breadcrumb")).toContainText("Azure SQL");
    await expect(page.getByTestId("drill-back")).toBeVisible();
    await expect(page.getByTestId("records-section")).toBeVisible();
  });

  test("percentage sort does not let tiny resources outrank large absolute changes by default", async ({ page }) => {
    await page.goto("/comparison?preset=week_to_date&group=resource");
    const first = page.getByTestId("contribution-grid").locator("tbody tr").first();
    await expect(first).toContainText("aks-userpool-27182818-vmss");
  });
});

test.describe("Cost Anomalies", () => {
  test("list -> detail separates measured facts from suggested steps", async ({ page }) => {
    await page.goto("/anomalies");
    await expect(page.getByTestId("anomalies-table")).toContainText("New expensive resource");
    await page.getByTestId("anomalies-table").getByText(/New expensive resource/).first().click();
    await expect(page.getByTestId("anomaly-detail")).toBeVisible();
    await expect(page.getByTestId("anomaly-ref")).toContainText("ANM-");
    await expect(page.getByTestId("measured-facts")).toContainText("first appeared in billing");
    await expect(page.getByTestId("suggested-steps")).toContainText(/not confirmed/i);
    await expect(page.getByTestId("echart-anomaly-trend")).toBeVisible();
  });
});

test.describe("Resource Analysis", () => {
  test("server-side search, detail page and meter-level decomposition", async ({ page }) => {
    await page.goto("/resources?preset=week_to_date");
    await page.getByTestId("resource-search").fill("sqldb-app2-prod-reporting");
    await expect(page.getByTestId("resources-table").locator("tbody tr")).toHaveCount(1);
    await page.getByTestId("resources-table").getByText("sqldb-app2-prod-reporting").click();
    await expect(page).toHaveURL(/\/resources\/\d+/);
    await expect(page.getByTestId("resource-info")).toContainText("Application 2");
    await expect(page.getByTestId("resource-decomp-reconciled")).toContainText(/exact/i);
    await expect(page.getByTestId("confirmed-facts")).toContainText("Business Critical");
    await expect(page.getByTestId("hypotheses")).toContainText(/unverified/i);
    await expect(page.getByTestId("resource-records-table")).toContainText("vCore");
  });
});

test.describe("Cost Investigation", () => {
  test("AKS increase is attributed to usage quantity, not price", async ({ page }) => {
    await page.goto("/investigation?preset=week_to_date&svc=Azure%20Kubernetes%20Service");
    await expect(page.getByTestId("investigation-summary")).toContainText("$4,500.00");
    await expect(page.getByTestId("investigation-reconciled")).toBeVisible();
    // the AKS node pool meter shows a quantity increase at an unchanged unit price
    await expect(page.getByTestId("investigation-meters")).toContainText("E16s v5");
  });
});
