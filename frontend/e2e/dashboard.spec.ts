import { expect, test, type Page } from "@playwright/test";
import { respond } from "../src/test/fixtures";

const PAGES = [
  { path: "/", heading: "Segmentation + churn" },
  { path: "/segments", heading: "Customer segmentation" },
  { path: "/segment-profiles", heading: "Segment profiles" },
  { path: "/churn-risk", heading: "Churn risk" },
  { path: "/explainability", heading: "Explain churn drivers with SHAP" },
  { path: "/simulator", heading: "Retention simulator" },
  { path: "/model-performance", heading: "Model performance" },
  { path: "/methodology", heading: "Data and methodology" },
];

async function mockApi(page: Page, failing?: string) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (failing && url.includes(failing)) {
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Database temporarily unavailable" }) });
    }
    const { status, body } = respond(url);
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test.describe("every page", () => {
  for (const p of PAGES) {
    test(`${p.path} renders, has one h1 and no horizontal overflow`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      await mockApi(page);
      await page.goto(p.path);
      await expect(page.getByRole("heading", { level: 1, name: p.heading })).toBeVisible();
      await expect(page.locator("h1")).toHaveCount(1);
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      expect(errors).toEqual([]);
    });
  }
});

test("navigation works on desktop and through the mobile menu", async ({ page, viewport }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByText("Fixture takeaway sentence.")).toBeVisible();
  if ((viewport?.width ?? 1440) < 1024) {
    await page.getByRole("button", { name: "Menu" }).click();
    await page.locator("#mobile-nav").getByRole("link", { name: /Retention Simulator/ }).click();
  } else {
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: /Retention Simulator/ }).click();
  }
  await expect(page).toHaveURL(/\/simulator$/);
  await expect(page.getByRole("heading", { level: 1, name: "Retention simulator" })).toBeVisible();
});

test("simulator recalculates when assumptions change", async ({ page }) => {
  await mockApi(page);
  await page.goto("/simulator");
  const banner = page.getByRole("note", { name: "Decision" });
  await expect(banner).toContainText("Targeting 1 customers by risk alone");
  await page.getByLabel("Customers targeted (% of scored)").fill("50");
  await expect(banner).toContainText("Targeting 2 customers");
  await page.getByRole("radio", { name: "Highest risk × value" }).click();
  await expect(banner).toContainText("£914");
  await expect(page.getByText(/Fixture disclaimer: scenario estimates only/)).toBeVisible();
});

test("churn risk filters update the URL and the list", async ({ page }) => {
  await mockApi(page);
  await page.goto("/churn-risk");
  await expect(page.getByText("40 customers")).toBeVisible();
  await page.getByLabel("Top-10% cohort only").click();
  await expect(page).toHaveURL(/top=1/);
  await expect(page.getByText("4 customers")).toBeVisible();
  await page.getByRole("button", { name: /Open details for customer/ }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("API failure shows an error and retry, never fabricated numbers", async ({ page }) => {
  await mockApi(page, "/summary");
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Database temporarily unavailable");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByText("0.712")).toHaveCount(0);
});

test("skip link and keyboard focus are available", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
});
