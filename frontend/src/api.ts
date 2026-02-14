import { getLogger } from "./logger";

export type TodoItem = {
  id: string;
  title: string;
  status: "pending" | "in_progress" | "done" | "completed" | "failed";
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

export async function chatStream(
  thread_id: string,
  user_id: string,
  message: string,
  onEvent: (event: any) => void
): Promise<void> {
  logger.debug("chat stream request", { thread_id, user_id });
  
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id, user_id, message }),
  });

  if (!response.ok) {
    logger.error("chat stream error", { status: response.status });
    throw new Error(await response.text());
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  
  if (!reader) return;

  let buffer = "";
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    
    // Split by double newline (SSE standard)
    const lines = buffer.split("\n\n");
    // Keep the incomplete last part in buffer
    buffer = lines.pop() || "";
    
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      
      const dataStr = trimmed.slice(6);
      if (dataStr === "[DONE]") return;
      
      try {
        const event = JSON.parse(dataStr);
        onEvent(event);
      } catch (e) {
        logger.warn("failed to parse sse event", { dataStr, e });
      }
    }
  }
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
