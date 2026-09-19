"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
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
import { createId, initialData, moveCard, type BoardData } from "@/lib/kanban";

const AUTH_STORAGE_KEY = "pm-authenticated";
const MVP_USERNAME = "user";
const MVP_PASSWORD = "password";

export const KanbanBoard = () => {
  const [board, setBoard] = useState<BoardData>(() => initialData);
  const [activeCardId, setActiveCardId] = useState<string | null>(null);
  const [isAuthReady, setIsAuthReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [syncMessage, setSyncMessage] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "I can summarize progress and update cards when you ask.",
    },
  ]);
  const [chatError, setChatError] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    setIsAuthenticated(window.localStorage.getItem(AUTH_STORAGE_KEY) === "true");
    setIsAuthReady(true);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    })
  );

  const cardsById = useMemo(() => board.cards, [board.cards]);

  const persistBoard = async (nextBoard: BoardData) => {
    if (typeof fetch !== "function") {
      return;
    }

    try {
      const response = await fetch("/api/board", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: MVP_USERNAME,
          board: nextBoard,
        }),
      });

      if (!response.ok) {
        throw new Error(`Persist failed with status ${response.status}`);
      }

      const payload = (await response.json()) as { board: BoardData };
      setBoard(payload.board);
      setSyncMessage("");
    } catch {
      setSyncMessage("Working locally. Backend sync is currently unavailable.");
    }
  };

  const sendChatMessage = async (message: string) => {
    setChatError("");
    const nextMessages = [...chatMessages, { role: "user", content: message } as const];
    setChatMessages(nextMessages);
    setIsChatLoading(true);

    try {
      const response = await fetch("/api/ai/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: MVP_USERNAME,
          message,
          history: nextMessages,
        }),
      });

      if (!response.ok) {
        throw new Error(`AI chat failed with status ${response.status}`);
      }

      const payload = (await response.json()) as {
        assistantResponse: string;
        boardUpdated: boolean;
        board: BoardData;
      };

      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: payload.assistantResponse },
      ]);

      if (payload.boardUpdated) {
        setBoard(payload.board);
        setSyncMessage("Board updated by AI.");
      }
    } catch {
      setChatError("AI request failed. Please try again.");
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "I could not reach the AI service right now.",
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated || typeof fetch !== "function") {
      return;
    }

    let cancelled = false;

    const loadBoard = async () => {
      try {
        const response = await fetch(`/api/board?username=${MVP_USERNAME}`);
        if (!response.ok) {
          throw new Error(`Load failed with status ${response.status}`);
        }
        const payload = (await response.json()) as { board: BoardData };
        if (!cancelled) {
          setBoard(payload.board);
          setSyncMessage("");
        }
      } catch {
        if (!cancelled) {
          setBoard(initialData);
          setSyncMessage("Working locally. Backend sync is currently unavailable.");
        }
      }
    };

    void loadBoard();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  const handleDragStart = (event: DragStartEvent) => {
    setActiveCardId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveCardId(null);

    if (!over || active.id === over.id) {
      return;
    }

    setBoard((prev) => {
      const nextBoard = {
        ...prev,
        columns: moveCard(prev.columns, active.id as string, over.id as string),
      };
      void persistBoard(nextBoard);
      return nextBoard;
    });
  };

  const handleRenameColumn = (columnId: string, title: string) => {
    setBoard((prev) => {
      const nextBoard = {
        ...prev,
        columns: prev.columns.map((column) =>
          column.id === columnId ? { ...column, title } : column
        ),
      };
      void persistBoard(nextBoard);
      return nextBoard;
    });
  };

  const handleAddCard = (columnId: string, title: string, details: string) => {
    const id = createId("card");
    setBoard((prev) => {
      const nextBoard = {
        ...prev,
        cards: {
          ...prev.cards,
          [id]: { id, title, details: details || "No details yet." },
        },
        columns: prev.columns.map((column) =>
          column.id === columnId
            ? { ...column, cardIds: [...column.cardIds, id] }
            : column
        ),
      };
      void persistBoard(nextBoard);
      return nextBoard;
    });
  };

  const handleDeleteCard = (columnId: string, cardId: string) => {
    setBoard((prev) => {
      const nextBoard = {
        ...prev,
        cards: Object.fromEntries(
          Object.entries(prev.cards).filter(([id]) => id !== cardId)
        ),
        columns: prev.columns.map((column) =>
          column.id === columnId
            ? {
                ...column,
                cardIds: column.cardIds.filter((id) => id !== cardId),
              }
            : column
        ),
      };
      void persistBoard(nextBoard);
      return nextBoard;
    });
  };

  const activeCard = activeCardId ? cardsById[activeCardId] : null;

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
    setUsername("");
    setPassword("");
    setAuthError("");
    setSyncMessage("");
    setChatError("");
    setChatMessages([
      {
        role: "assistant",
        content: "I can summarize progress and update cards when you ask.",
      },
    ]);
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
