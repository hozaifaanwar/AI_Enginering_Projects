import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KanbanBoard } from "@/components/KanbanBoard";
import { installFakeApi } from "@/test/fakeApi";

const login = async () => {
  await userEvent.type(screen.getByLabelText(/username/i), "user");
  await userEvent.type(screen.getByLabelText(/password/i), "password");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
};

const renderBoard = async () => {
  render(<KanbanBoard />);
  await login();
  await screen.findAllByTestId(/^column-/);
};

const getFirstColumn = () => screen.getAllByTestId(/^column-/)[0];

const addCard = async (title: string) => {
  const column = getFirstColumn();
  await userEvent.click(within(column).getByRole("button", { name: /add a card/i }));
  await userEvent.type(within(column).getByPlaceholderText(/card title/i), title);
  await userEvent.click(within(column).getByRole("button", { name: /add card/i }));
};

describe("KanbanBoard", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requires login before showing the board", () => {
    render(<KanbanBoard />);
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.queryByText("Kanban Studio")).not.toBeInTheDocument();
  });

  it("shows an error for invalid credentials", async () => {
    render(<KanbanBoard />);
    await userEvent.type(screen.getByLabelText(/username/i), "wrong");
    await userEvent.type(screen.getByLabelText(/password/i), "credentials");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
  });

  it("loads five columns from the backend", async () => {
    installFakeApi();
    await renderBoard();
    expect(screen.getAllByTestId(/^column-/)).toHaveLength(5);
  });

  it("shows a load error and recovers on retry", async () => {
    const { options } = installFakeApi({ loadStatus: 500 });
    render(<KanbanBoard />);
    await login();
    expect(await screen.findByText(/could not load the board/i)).toBeInTheDocument();

    options.loadStatus = undefined;
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findAllByTestId(/^column-/)).toHaveLength(5);
  });

  it("saves a column rename once, on blur", async () => {
    const { state } = installFakeApi();
    await renderBoard();
    const input = within(getFirstColumn()).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");
    expect(state.putRevisions).toHaveLength(0);

    await userEvent.tab();
    await waitFor(() => expect(state.board.columns[0].title).toBe("New Name"));
    expect(state.putRevisions).toEqual([1]);
  });

  it("adds, edits and removes a card", async () => {
    const { state } = installFakeApi();
    await renderBoard();
    await addCard("New card");
    const column = getFirstColumn();
    expect(within(column).getByText("New card")).toBeInTheDocument();

    await userEvent.click(within(column).getByRole("button", { name: /edit new card/i }));
    const titleInput = within(column).getByLabelText("Card title");
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Edited card");
    await userEvent.click(within(column).getByRole("button", { name: "Save" }));
    expect(within(column).getByText("Edited card")).toBeInTheDocument();
    await waitFor(() =>
      expect(Object.values(state.board.cards).some((card) => card.title === "Edited card")).toBe(true)
    );

    await userEvent.click(within(column).getByRole("button", { name: /delete edited card/i }));
    expect(within(column).queryByText("Edited card")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(Object.values(state.board.cards).some((card) => card.title === "Edited card")).toBe(false)
    );
  });

  it("sends edits made during a save after it completes, without conflicts", async () => {
    const { state } = installFakeApi({ putDelayMs: 100 });
    await renderBoard();
    await addCard("First");
    await addCard("Second");
    await addCard("Third");

    await waitFor(() => {
      const titles = Object.values(state.board.cards).map((card) => card.title);
      expect(titles).toEqual(expect.arrayContaining(["First", "Second", "Third"]));
    });
    // Each save used the revision returned by the previous one, so none conflicted.
    expect(state.putRevisions).toEqual(state.putRevisions.map((_, index) => index + 1));
    expect(screen.queryByText(/changed elsewhere|could not save/i)).not.toBeInTheDocument();
  });

  it("applies AI board updates and shows AI error details", async () => {
    installFakeApi({
      chat: ({ message }, state) => {
        if (message === "break") {
          return { status: 502, body: { detail: "AI proposed an invalid change." } };
        }
        state.board.columns[0].title = "AI Renamed";
        state.revision += 1;
        return {
          status: 200,
          body: {
            assistantResponse: "Renamed it.",
            boardUpdated: true,
            operationsApplied: 1,
            revision: state.revision,
            board: state.board,
          },
        };
      },
    });
    await renderBoard();
    const textbox = screen.getByPlaceholderText(/example:/i);

    await userEvent.type(textbox, "rename");
    await userEvent.click(screen.getByRole("button", { name: /send to ai/i }));
    expect(await screen.findByText("Renamed it.")).toBeInTheDocument();
    expect(within(getFirstColumn()).getByLabelText("Column title")).toHaveValue("AI Renamed");

    await userEvent.type(textbox, "break");
    await userEvent.click(screen.getByRole("button", { name: /send to ai/i }));
    expect(await screen.findByText(/AI proposed an invalid change/)).toBeInTheDocument();
  });

  it("allows logout", async () => {
    installFakeApi();
    await renderBoard();
    await userEvent.click(screen.getByRole("button", { name: /log out/i }));
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });
});
