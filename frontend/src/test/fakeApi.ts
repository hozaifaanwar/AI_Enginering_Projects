import { vi } from "vitest";
import type { ChatMessage } from "@/components/AIChatSidebar";
import type { BoardData } from "@/lib/kanban";
import { seedBoard } from "@/test/boardFixture";

type FakeResponse = { status: number; body: unknown };

export type FakeApiState = {
  board: BoardData;
  revision: number;
  putRevisions: number[];
};

type FakeApiOptions = {
  loadStatus?: number;
  putDelayMs?: number;
  chat?: (body: { message: string; history: ChatMessage[] }, state: FakeApiState) => FakeResponse;
};

const toResponse = ({ status, body }: FakeResponse) =>
  ({ ok: status < 300, status, json: async () => body }) as Response;

// In-memory stand-in for the backend board and chat endpoints.
export const installFakeApi = (options: FakeApiOptions = {}) => {
  const state: FakeApiState = {
    board: structuredClone(seedBoard),
    revision: 1,
    putRevisions: [],
  };

  const handle = async (url: string, init?: RequestInit): Promise<FakeResponse> => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;

    if (url === "/api/board" && method === "GET") {
      if (options.loadStatus) {
        return { status: options.loadStatus, body: { detail: "Load failed." } };
      }
      return { status: 200, body: { board: state.board, revision: state.revision } };
    }
    if (url === "/api/board" && method === "PUT") {
      state.putRevisions.push(body.revision);
      if (options.putDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.putDelayMs));
      }
      if (body.revision !== state.revision) {
        return { status: 409, body: { detail: "Board has changed." } };
      }
      state.board = body.board;
      state.revision += 1;
      return { status: 200, body: { board: state.board, revision: state.revision } };
    }
    if (url === "/api/ai/chat" && options.chat) {
      return options.chat(body, state);
    }
    return { status: 404, body: { detail: "Not found." } };
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => toResponse(await handle(url, init)))
  );
  return { state, options };
};
