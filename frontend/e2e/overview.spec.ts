import { expect, test } from "@playwright/test";

test.describe("Executive Overview", () => {
  test("shows the demonstration week-over-week KPIs and DEMO labelling", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("demo-banner")).toContainText("DEMO DATA");
    await expect(page.getByTestId("kpi-current_week-value")).toHaveText("$110K");
    await expect(page.getByTestId("kpi-current_week")).toContainText("+10.0%");
    await expect(page.getByTestId("kpi-previous_week-value")).toHaveText("$100K");
    await expect(page.getByTestId("kpi-forecast")).toContainText("Projection");
    await expect(page.getByTestId("freshness")).toContainText("Data through");
  });

  test("every chart offers a table view", async ({ page }) => {
    await page.goto("/");
    const trend = page.getByTestId("trend");
    await trend.getByRole("button", { name: "Table view" }).click();
    await expect(trend.getByRole("table")).toBeVisible();
    await trend.getByRole("button", { name: "Chart view" }).click();
    await expect(trend.getByRole("img")).toBeVisible();
  });

  test("clicking the current-week KPI opens the weekly comparison", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("kpi-current_week").click();
    await expect(page).toHaveURL(/\/comparison\?.*preset=week_to_date/);
  });
});
