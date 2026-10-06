"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  closestCorners,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { AIChatSidebar, type ChatMessage } from "@/components/AIChatSidebar";
import { KanbanColumn } from "@/components/KanbanColumn";
import { KanbanCardPreview } from "@/components/KanbanCardPreview";
import { createId, moveCard, type BoardData } from "@/lib/kanban";

const AUTH_STORAGE_KEY = "pm-authenticated";
const MVP_USERNAME = "user";
const MVP_PASSWORD = "password";
const DEMO_AUTH_HEADERS = {
  "X-Demo-User": MVP_USERNAME,
  "X-Demo-Password": MVP_PASSWORD,
};
const INITIAL_CHAT_MESSAGES: ChatMessage[] = [
  {
    role: "assistant",
    content: "I can summarize progress and update cards when you ask.",
  },
];

type BoardPayload = { board: BoardData; revision: number };

const apiFetch = (path: string, init?: RequestInit) =>
  fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...DEMO_AUTH_HEADERS },
  });

const errorMessage = async (response: Response) => {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string"
    ? body.detail
    : `Request failed with status ${response.status}.`;
};

export const KanbanBoard = () => {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [syncMessage, setSyncMessage] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [chatError, setChatError] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);
  const revisionRef = useRef(0);
  // Saves run one at a time; edits made while a save is in flight are sent next.
  const pendingBoardRef = useRef<BoardData | null>(null);
  const savingRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    setIsAuthenticated(window.localStorage.getItem(AUTH_STORAGE_KEY) === "true");
    setIsAuthReady(true);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    })
  );

  const loadBoard = async () => {
    try {
      const response = await apiFetch("/api/board");
      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }
      const payload = (await response.json()) as BoardPayload;
      revisionRef.current = payload.revision;
      setBoard(payload.board);
    } catch (error) {
      setLoadError(`Could not load the board. ${(error as Error).message}`);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      void loadBoard();
    }
  }, [isAuthenticated]);

  const saveBoard = async () => {
    try {
      while (pendingBoardRef.current) {
        const boardToSave = pendingBoardRef.current;
        pendingBoardRef.current = null;
        const response = await apiFetch("/api/board", {
          method: "PUT",
          body: JSON.stringify({ revision: revisionRef.current, board: boardToSave }),
        });
        if (response.status === 409) {
          await loadBoard();
          pendingBoardRef.current = null;
          setSyncMessage("The board changed elsewhere. Reloaded the latest version.");
          return;
        }
        if (!response.ok) {
          throw new Error(await errorMessage(response));
        }
        revisionRef.current = ((await response.json()) as BoardPayload).revision;
      }
      setSyncMessage("");
    } catch (error) {
      setSyncMessage(`Could not save changes. ${(error as Error).message}`);
    }
  };

  const updateBoard = (change: (current: BoardData) => BoardData) => {
    if (!board) {
      return;
    }
    const nextBoard = change(board);
    setBoard(nextBoard);
    pendingBoardRef.current = nextBoard;
    if (!savingRef.current) {
      savingRef.current = saveBoard().finally(() => {
        savingRef.current = null;
      });
    }
  };

  const sendChatMessage = async (message: string) => {
    setChatError("");
    const history = chatMessages;
    setChatMessages([...history, { role: "user", content: message }]);
    setIsChatLoading(true);

    try {
      // The AI applies changes to the saved board, so pending edits go first.
      await savingRef.current;
      const response = await apiFetch("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message, history }),
      });
      if (!response.ok) {
        throw new Error(await errorMessage(response));
      }

      const payload = (await response.json()) as BoardPayload & {
        assistantResponse: string;
        boardUpdated: boolean;
      };
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: payload.assistantResponse },
      ]);
      if (payload.boardUpdated) {
        revisionRef.current = payload.revision;
        setBoard(payload.board);
        setSyncMessage("Board updated by AI.");
      }
    } catch (error) {
      setChatError(`AI request failed. ${(error as Error).message}`);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleDragStart = (event: DragStartEvent) => {
    setActiveCardId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveCardId(null);

    if (!over || active.id === over.id) {
      return;
    }

    updateBoard((current) => ({
      ...current,
      columns: moveCard(current.columns, active.id as string, over.id as string),
    }));
  };

  const handleRenameColumn = (columnId: string, title: string) => {
    updateBoard((current) => ({
      ...current,
      columns: current.columns.map((column) =>
        column.id === columnId ? { ...column, title } : column
      ),
    }));
  };

  const handleAddCard = (columnId: string, title: string, details: string) => {
    const id = createId("card");
    updateBoard((current) => ({
      ...current,
      cards: {
        ...current.cards,
        [id]: { id, title, details: details || "No details yet." },
      },
      columns: current.columns.map((column) =>
        column.id === columnId
          ? { ...column, cardIds: [...column.cardIds, id] }
          : column
      ),
    }));
  };

  const handleEditCard = (cardId: string, title: string, details: string) => {
    updateBoard((current) => ({
      ...current,
      cards: { ...current.cards, [cardId]: { id: cardId, title, details } },
    }));
  };

  const handleDeleteCard = (columnId: string, cardId: string) => {
    updateBoard((current) => ({
      ...current,
      cards: Object.fromEntries(
        Object.entries(current.cards).filter(([id]) => id !== cardId)
      ),
      columns: current.columns.map((column) =>
        column.id === columnId
          ? {
              ...column,
              cardIds: column.cardIds.filter((id) => id !== cardId),
            }
          : column
      ),
    }));
  };

  const handleLogin = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (username === MVP_USERNAME && password === MVP_PASSWORD) {
      window.localStorage.setItem(AUTH_STORAGE_KEY, "true");
      setIsAuthenticated(true);
      setAuthError("");
      setPassword("");
      return;
    }

    setAuthError("Invalid credentials. Use user / password.");
  };

  const handleLogout = () => {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    setIsAuthenticated(false);
    setBoard(null);
    setLoadError("");
    setUsername("");
    setPassword("");
    setAuthError("");
    setSyncMessage("");
    setChatError("");
    setChatMessages(INITIAL_CHAT_MESSAGES);
  };

  if (!isAuthReady) {
    return (
      <main className="mx-auto flex min-h-screen max-w-[680px] items-center justify-center px-6 py-12">
        <p className="text-sm font-medium text-[var(--gray-text)]">Loading…</p>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="mx-auto flex min-h-screen max-w-[680px] items-center px-6 py-12">
        <section className="w-full rounded-[28px] border border-[var(--stroke)] bg-white/90 p-8 shadow-[var(--shadow)]">
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-[var(--gray-text)]">
            Project Management MVP
          </p>
          <h1 className="mt-3 font-display text-4xl font-semibold text-[var(--navy-dark)]">
            Sign in
          </h1>
          <p className="mt-3 text-sm text-[var(--gray-text)]">
            Use the demo credentials to access your board.
          </p>

          <form className="mt-8 grid gap-5" onSubmit={handleLogin}>
            <label className="grid gap-2 text-sm font-medium text-[var(--navy-dark)]">
              Username
              <input
                name="username"
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                className="h-11 rounded-xl border border-[var(--stroke)] px-3 outline-none transition focus:border-[var(--primary-blue)]"
              />
            </label>

            <label className="grid gap-2 text-sm font-medium text-[var(--navy-dark)]">
              Password
              <input
                name="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="h-11 rounded-xl border border-[var(--stroke)] px-3 outline-none transition focus:border-[var(--primary-blue)]"
              />
            </label>

            {authError ? (
              <p className="text-sm font-medium text-[var(--secondary-purple)]">{authError}</p>
            ) : null}

            <button
              type="submit"
              className="h-11 rounded-xl bg-[var(--secondary-purple)] px-4 text-sm font-semibold text-white transition hover:opacity-90"
            >
              Sign in
            </button>

            <p className="text-xs text-[var(--gray-text)]">Demo: user / password</p>
          </form>
        </section>
      </main>
    );
  }

  if (!board) {
    return (
      <main className="mx-auto flex min-h-screen max-w-[680px] flex-col items-center justify-center gap-4 px-6 py-12">
        {loadError ? (
          <>
            <p className="text-sm font-medium text-[var(--secondary-purple)]">{loadError}</p>
            <button
              type="button"
              onClick={() => {
                setLoadError("");
                void loadBoard();
              }}
              className="h-11 rounded-xl bg-[var(--secondary-purple)] px-4 text-sm font-semibold text-white transition hover:opacity-90"
            >
              Retry
            </button>
          </>
        ) : (
          <p className="text-sm font-medium text-[var(--gray-text)]">Loading board…</p>
        )}
      </main>
    );
  }

  const activeCard = activeCardId ? board.cards[activeCardId] : null;

  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute left-0 top-0 h-[420px] w-[420px] -translate-x-1/3 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,_rgba(32,157,215,0.25)_0%,_rgba(32,157,215,0.05)_55%,_transparent_70%)]" />
      <div className="pointer-events-none absolute bottom-0 right-0 h-[520px] w-[520px] translate-x-1/4 translate-y-1/4 rounded-full bg-[radial-gradient(circle,_rgba(117,57,145,0.18)_0%,_rgba(117,57,145,0.05)_55%,_transparent_75%)]" />

      <main className="relative mx-auto flex min-h-screen max-w-[1500px] flex-col gap-10 px-6 pb-16 pt-12">
        <header className="flex flex-col gap-6 rounded-[32px] border border-[var(--stroke)] bg-white/80 p-8 shadow-[var(--shadow)] backdrop-blur">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--gray-text)]">
                Single Board Kanban
              </p>
              <h1 className="mt-3 font-display text-4xl font-semibold text-[var(--navy-dark)]">
                Kanban Studio
              </h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-[var(--gray-text)]">
                Keep momentum visible. Rename columns, drag cards between stages,
                and capture quick notes without getting buried in settings.
              </p>
              <button
                type="button"
                onClick={handleLogout}
                className="mt-5 rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)] transition hover:border-[var(--primary-blue)] hover:text-[var(--primary-blue)]"
              >
                Log out
              </button>
            </div>
            <div className="rounded-2xl border border-[var(--stroke)] bg-[var(--surface)] px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-[var(--gray-text)]">
                Focus
              </p>
              <p className="mt-2 text-lg font-semibold text-[var(--primary-blue)]">
                One board. Five columns. Zero clutter.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {board.columns.map((column) => (
              <div
                key={column.id}
                className="flex items-center gap-2 rounded-full border border-[var(--stroke)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--navy-dark)]"
              >
                <span className="h-2 w-2 rounded-full bg-[var(--accent-yellow)]" />
                {column.title}
              </div>
            ))}
          </div>
          {syncMessage ? (
            <p className="text-sm font-medium text-[var(--secondary-purple)]">{syncMessage}</p>
          ) : null}
        </header>

        <div className="grid gap-6 lg:grid-cols-[1fr_330px]">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCorners}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <section className="grid gap-6 lg:grid-cols-5">
              {board.columns.map((column) => (
                <KanbanColumn
                  key={column.id}
                  column={column}
                  cards={column.cardIds.map((cardId) => board.cards[cardId])}
                  onRename={handleRenameColumn}
                  onAddCard={handleAddCard}
                  onEditCard={handleEditCard}
                  onDeleteCard={handleDeleteCard}
                />
              ))}
            </section>
            <DragOverlay>
              {activeCard ? (
                <div className="w-[260px]">
                  <KanbanCardPreview card={activeCard} />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>

          <AIChatSidebar
            messages={chatMessages}
            isLoading={isChatLoading}
            errorMessage={chatError}
            onSendMessage={sendChatMessage}
          />
        </div>
      </main>
    </div>
  );
};
