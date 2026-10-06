import { expect, test } from "@playwright/test";
import { mockBackend } from "./mockBackend";

const signIn = async (page: import("@playwright/test").Page) => {
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: /sign in/i }).click();
};

test("loads the kanban board", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("adds a card to a column", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Playwright card");
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Playwright card")).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  const card = page.getByTestId("card-card-1");
  const targetColumn = page.getByTestId("column-col-review");
  const cardBox = await card.boundingBox();
  const columnBox = await targetColumn.boundingBox();
  if (!cardBox || !columnBox) {
    throw new Error("Unable to resolve drag coordinates.");
  }

  await page.mouse.move(
    cardBox.x + cardBox.width / 2,
    cardBox.y + cardBox.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    columnBox.x + columnBox.width / 2,
    columnBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();
  await expect(targetColumn.getByTestId("card-card-1")).toBeVisible();
});

test("logs out and returns to sign in", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  await expect(page.getByText(/demo: user \/ password/i)).toBeVisible();
});

test("shows ai sidebar and handles chat errors", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  await expect(page.getByRole("heading", { name: /ask and update/i })).toBeVisible();
  await page
    .getByPlaceholder(/example: move qa micro-interactions to done/i)
    .fill("Summarize this board");
  await page.getByRole("button", { name: /send to ai/i }).click();
  await expect(page.getByText(/AI request failed. OpenRouter is unavailable./i)).toBeVisible();
});

test("edits a card", async ({ page }) => {
  await mockBackend(page);
  await page.goto("/");
  await signIn(page);
  const card = page.getByTestId("card-card-1");
  await card.getByRole("button", { name: /edit align roadmap themes/i }).click();
  await card.getByLabel("Card title").fill("Edited roadmap");
  await card.getByLabel("Card details").fill("Edited in e2e.");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(card.getByText("Edited roadmap")).toBeVisible();
  await expect(card.getByText("Edited in e2e.")).toBeVisible();
});
