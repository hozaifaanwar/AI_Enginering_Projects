import type { Page } from "@playwright/test";
import { seedBoard } from "../src/test/boardFixture";

// Stands in for the FastAPI backend when running against the Next.js dev server.
export const mockBackend = async (page: Page) => {
  let board = structuredClone(seedBoard);
  let revision = 1;

  await page.route("**/api/board", async (route) => {
    const request = route.request();
    if (request.method() === "PUT") {
      const body = request.postDataJSON();
      if (body.revision !== revision) {
        await route.fulfill({ status: 409, json: { detail: "Board has changed." } });
        return;
      }
      board = body.board;
      revision += 1;
    }
    await route.fulfill({ json: { username: "user", revision, board } });
  });

  await page.route("**/api/ai/chat", (route) =>
    route.fulfill({ status: 502, json: { detail: "OpenRouter is unavailable." } })
  );
};
