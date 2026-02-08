import { getLogger } from "./logger";

export type TodoItem = {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "done";
};

export type ChatResponse = {
  thread_id: string;
  user_id: string;
  reply: string;
  plan: string[];
  todos: TodoItem[];
  memories: Array<Record<string, unknown>>;
};

const logger = getLogger("api");

export async function chat(
  thread_id: string,
  user_id: string,
  message: string
): Promise<ChatResponse> {
  logger.debug("chat request", { thread_id, user_id });
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id, user_id, message }),
  });
  if (!res.ok) {
    logger.error("chat response error", { status: res.status });
    throw new Error(await res.text());
  }
  logger.debug("chat response ok");
  return res.json();
}

export async function getTodos(thread_id: string): Promise<TodoItem[]> {
  logger.debug("todos request", { thread_id });
  const res = await fetch(`/api/todos?thread_id=${encodeURIComponent(thread_id)}`);
  if (!res.ok) {
    logger.error("todos response error", { status: res.status });
    throw new Error(await res.text());
  }
  return res.json();
}

export async function getSessions(user_id: string): Promise<string[]> {
  logger.debug("sessions request", { user_id });
  const res = await fetch(`/api/sessions?user_id=${encodeURIComponent(user_id)}`);
  if (!res.ok) {
    logger.error("sessions response error", { status: res.status });
    throw new Error(await res.text());
  }
  return res.json();
}
