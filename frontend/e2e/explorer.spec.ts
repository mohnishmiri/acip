import { expect, test, type Page } from "@playwright/test";

const SCENARIO = "/explorer?preset=week_to_date&group=service_category";

async function expectScenarioTotals(page: Page) {
  await expect(page.getByTestId("total-current")).toContainText("$110,000.00");
  await expect(page.getByTestId("total-previous")).toContainText("$100,000.00");
  await expect(page.getByTestId("total-diff")).toContainText("$10,000.00");
  await expect(page.getByTestId("total-pct")).toContainText("10.0%");
}

test.describe("Cost Explorer", () => {
  test("weekly scenario totals are calculated: 100,000 -> 110,000 (+10%)", async ({ page }) => {
    await page.goto(SCENARIO);
    await expectScenarioTotals(page);
  });

  test("switching visualisation keeps filters and reuses the same query result", async ({ page }) => {
    let explorerCalls = 0;
    page.on("request", (r) => {
      if (r.url().includes("/api/v1/costs/explorer")) explorerCalls++;
    });
    await page.goto(`${SCENARIO}&app=1&cost=actual`);
    await expect(page.getByTestId("total-current")).not.toContainText("…");
    const callsAfterLoad = explorerCalls;
    for (const chart of ["grouped", "stacked", "line", "area", "stacked_area", "waterfall", "donut", "treemap", "table", "bar"]) {
      await page.getByTestId(`chart-${chart}`).click();
      await expect(page).toHaveURL(new RegExp(`chart=${chart}|^(?!.*chart=)`));
      await expect(page).toHaveURL(/preset=week_to_date/);
      await expect(page).toHaveURL(/app=1/);
      await expect(page.getByTestId("filter-application")).toContainText("Application 1");
    }
    expect(explorerCalls).toBe(callsAfterLoad); // chart switching never refetches
  });

  test("waterfall explains the +10,000 and reconciles", async ({ page }) => {
    await page.goto(`${SCENARIO}&chart=waterfall&top=4`);
    await expect(page.getByTestId("echart-waterfall")).toBeVisible();
    await expect(page.getByTestId("waterfall-reconciliation")).toContainText("$100,000.00 + $10,000.00 (+10.0%) = $110,000.00");
    await expect(page.getByTestId("waterfall-reconciliation")).toContainText("Reconciled exactly");
    const grid = page.getByTestId("explorer-grid");
    for (const svc of ["Azure Kubernetes Service", "Azure SQL", "Storage", "Networking"]) await expect(grid).toContainText(svc);
  });

  test("table click drills Azure SQL -> resources -> resource detail with breadcrumb", async ({ page }) => {
    await page.goto(SCENARIO);
    await page.getByTestId("explorer-grid").getByText("Azure SQL", { exact: true }).click();
    await expect(page.getByTestId("breadcrumb")).toContainText("Azure SQL");
    await expect(page.getByTestId("breadcrumb")).toContainText("by Resource Name");
    await expect(page.getByTestId("total-current")).toContainText("$22,000.00");
    const firstRow = page.getByTestId("explorer-grid").locator("tbody tr").first();
    await expect(firstRow).toContainText("sqldb-app2-prod-reporting");
    await page.getByTestId("drill-back").click();
    await expect(page.getByTestId("breadcrumb")).not.toContainText("Azure SQL");
    await expectScenarioTotals(page);
    await page.getByTestId("explorer-grid").getByText("Azure SQL", { exact: true }).click();
    await page.getByTestId("explorer-grid").getByText("sqldb-app2-prod-reporting").click();
    await expect(page).toHaveURL(/\/resources\/\d+/);
  });

  test("date selection and grouping changes update the result", async ({ page }) => {
    await page.goto(SCENARIO);
    await page.getByTestId("date-range").click();
    await page.getByRole("menuitem", { name: "Previous week" }).click();
    await expect(page).toHaveURL(/preset=previous_week/);
    await expect(page.getByTestId("total-current")).toContainText("$100,000.00");
    await page.getByTestId("group-by").click();
    await page.getByRole("option", { name: "Application" }).click();
    await expect(page.getByTestId("explorer-grid")).toContainText("Application 1");
    await expect(page.getByTestId("explorer-grid")).toContainText("Shared Services");
  });

  test("table export downloads a CSV", async ({ page }) => {
    await page.goto(SCENARIO);
    await page.getByTestId("export-explorer").click();
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: /CSV/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/^acip-explorer-.*\.csv$/);
  });

  test("shows an error state with retry when the API fails", async ({ page }) => {
    await page.route("**/api/v1/costs/explorer**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: { code: "internal_error", message: "Simulated failure" } }) }));
    await page.goto(SCENARIO);
    await expect(page.getByText("Unable to load data")).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  });
});
