import { createContext, useContext, useEffect, useState } from "react";
import type { TodoItem } from "./api";

type DeepAgentState = {
  threadId: string;
  userId: string;
  setThreadId: (value: string) => void;
  setUserId: (value: string) => void;
  sessions: string[];
  setSessions: (value: string[]) => void;
  createSession: () => string;
  todos: TodoItem[];
  setTodos: (value: TodoItem[]) => void;
  plan: string[];
  setPlan: (value: string[]) => void;
  planSummary: string;
  setPlanSummary: (value: string) => void;
  memories: Array<Record<string, unknown>>;
  setMemories: (value: Array<Record<string, unknown>>) => void;
};

const DeepAgentContext = createContext<DeepAgentState | null>(null);

function createUuid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function storageKey(userId: string) {
  return `deepagent:sessions:${userId}`;
}

function loadSessions(userId: string) {
  const raw = localStorage.getItem(storageKey(userId));
  return raw ? (JSON.parse(raw) as string[]) : [];
}

function saveSessions(userId: string, sessions: string[]) {
  localStorage.setItem(storageKey(userId), JSON.stringify(sessions));
}

export function DeepAgentProvider({ children }: { children: React.ReactNode }) {
  const initialUserId = "user-1";
  const initialSessions = loadSessions(initialUserId);
  const initialThreadId = initialSessions[0] ?? createUuid();
  const [userId, setUserId] = useState(initialUserId);
  const [sessions, setSessions] = useState<string[]>(initialSessions);
  const [threadId, setThreadId] = useState(initialThreadId);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [plan, setPlan] = useState<string[]>([]);
  const [planSummary, setPlanSummary] = useState<string>("");
  const [memories, setMemories] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    setTodos([]);
    setPlan([]);
    setPlanSummary("");
    setMemories([]);
  }, [threadId]);

  useEffect(() => {
    const loaded = loadSessions(userId);
    if (loaded.length === 0) {
      const nextId = createUuid();
      setSessions([nextId]);
      setThreadId(nextId);
      saveSessions(userId, [nextId]);
      return;
    }
    setSessions(loaded);
    if (!loaded.includes(threadId)) {
      setThreadId(loaded[0]);
    }
  }, [userId]);

  useEffect(() => {
    if (sessions.length > 0) {
      saveSessions(userId, sessions);
    }
  }, [userId, sessions]);

  function createSession() {
    const nextId = createUuid();
    const nextSessions = [nextId, ...sessions];
    setSessions(nextSessions);
    setThreadId(nextId);
    saveSessions(userId, nextSessions);
    return nextId;
  }

  return (
    <DeepAgentContext.Provider
      value={{
        threadId,
        userId,
        setThreadId,
        setUserId,
        sessions,
        setSessions,
        createSession,
        todos,
        setTodos,
        plan,
        setPlan,
        planSummary,
        setPlanSummary,
        memories,
        setMemories,
      }}
    >
      {children}
    </DeepAgentContext.Provider>
  );
}

export function useDeepAgent() {
  const ctx = useContext(DeepAgentContext);
  if (!ctx) {
    throw new Error("DeepAgentProvider missing");
  }
  return ctx;
}
