import { expect, test } from "@playwright/test";

const AUTH_HEADERS = {
  "X-Demo-User": "user",
  "X-Demo-Password": "password",
};

const signIn = async (page: import("@playwright/test").Page) => {
  await page.getByLabel("Username").fill("user");
  await page.getByLabel("Password").fill("password");
  await page.getByRole("button", { name: /sign in/i }).click();
};

test("persists a new card after refresh on integrated stack", async ({ page }) => {
  await page.goto("/");
  await signIn(page);

  const firstColumn = page.locator('[data-testid^="column-"]').first();
  await firstColumn.getByRole("button", { name: /add a card/i }).click();

  const cardTitle = `Integrated Persist ${Date.now()}`;
  await firstColumn.getByPlaceholder("Card title").fill(cardTitle);
  await firstColumn.getByPlaceholder("Details").fill("Integrated persistence check");
  await firstColumn.getByRole("button", { name: /add card/i }).click();

  await expect(firstColumn.getByText(cardTitle)).toBeVisible();
  await page.reload();
  await expect(firstColumn.getByText(cardTitle)).toBeVisible();
});

test("keeps a quickly typed column rename intact", async ({ page }) => {
  await page.goto("/");
  await signIn(page);

  const input = page.getByLabel("Column title").last();
  const original = await input.inputValue();
  await input.fill("");
  await input.pressSequentially("Renamed Quickly", { delay: 10 });
  await input.press("Enter");

  await page.reload();
  await expect(page.getByLabel("Column title").last()).toHaveValue("Renamed Quickly");

  await page.getByLabel("Column title").last().fill(original);
  await page.getByLabel("Column title").last().press("Enter");
  await page.reload();
  await expect(page.getByLabel("Column title").last()).toHaveValue(original);
});

test("persists a card edit after refresh", async ({ page }) => {
  await page.goto("/");
  await signIn(page);

  const firstColumn = page.locator('[data-testid^="column-"]').first();
  const card = firstColumn.locator('[data-testid^="card-"]').first();
  const cardTestId = await card.getAttribute("data-testid");
  await card.getByRole("button", { name: /^edit /i }).click();
  const editedTitle = `Edited ${Date.now()}`;
  await card.getByLabel("Card title").fill(editedTitle);
  await card.getByRole("button", { name: "Save" }).click();

  await page.reload();
  await expect(page.getByTestId(cardTestId!).getByText(editedTitle)).toBeVisible();
});

test("applies AI-driven update and refreshes board", async ({ page, request }) => {
  const ping = await request.post("/api/ai/ping", {
    headers: AUTH_HEADERS,
    data: { question: "2+2" },
  });
  test.skip(ping.status() !== 200, "OpenRouter connectivity is unavailable for this run.");

  const targetTitle = `AI Card ${Math.random().toString(36).slice(2, 6)}`;
  const aiResponse = await request.post("/api/ai/chat", {
    headers: AUTH_HEADERS,
    data: {
      message: `Add a card to the Backlog column titled '${targetTitle}' with details 'created by integrated test'.`,
      history: [],
    },
    timeout: 60_000,
  });
  expect(aiResponse.status()).toBe(200);

  const payload = (await aiResponse.json()) as {
    boardUpdated: boolean;
    board: {
      columns: { id: string; cardIds: string[] }[];
      cards: Record<string, { title: string }>;
    };
  };
  expect(payload.boardUpdated).toBe(true);
  const backlog = payload.board.columns.find((column) => column.id === "col-backlog")!;
  expect(backlog.cardIds.map((id) => payload.board.cards[id].title)).toContain(targetTitle);

  await page.goto("/");
  await signIn(page);
  await expect(page.getByText(targetTitle)).toBeVisible();
});
