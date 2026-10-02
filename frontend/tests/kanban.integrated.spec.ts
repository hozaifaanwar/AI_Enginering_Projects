import { expect, test } from "@playwright/test";

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

test("applies AI-driven update and refreshes board", async ({ page, request }) => {
  const ping = await request.post("/api/ai/ping", {
    headers: {
      "X-Demo-User": "user",
      "X-Demo-Password": "password",
      "Content-Type": "application/json",
    },
    data: { question: "2+2" },
  });
  test.skip(ping.status() !== 200, "OpenRouter connectivity is unavailable for this run.");

  const targetTitle = `AI Integrated ${Date.now()}`;
  let boardUpdated = false;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const aiResponse = await request.post("/api/ai/chat", {
      headers: {
        "X-Demo-User": "user",
        "X-Demo-Password": "password",
        "Content-Type": "application/json",
      },
      data: {
        username: "user",
        revision: null,
        message: `Return JSON with assistantResponse and operations. Add one card to col-backlog titled '${targetTitle}' with details 'created by integrated test'.`,
        history: [],
      },
    });

    if (aiResponse.status() !== 200) {
      continue;
    }

    const payload = (await aiResponse.json()) as {
      boardUpdated: boolean;
      board: {
        cards: Record<string, { title: string }>;
      };
    };

    const hasTargetCard = Object.values(payload.board.cards).some(
      (card) => card.title === targetTitle
    );
    if (payload.boardUpdated && hasTargetCard) {
      boardUpdated = true;
      break;
    }
  }

  expect(boardUpdated).toBeTruthy();

  await page.goto("/");
  await signIn(page);
  await expect(page.getByText(targetTitle)).toBeVisible();
  await page.reload();
  await expect(page.getByText(targetTitle)).toBeVisible();
});
