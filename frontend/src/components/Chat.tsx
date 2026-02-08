import { useEffect, useState } from "react";
import {
  Box,
  Button,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { chat, getSessions } from "../api";
import { useDeepAgent } from "../context";

export default function Chat() {
  const {
    threadId,
    userId,
    setThreadId,
    setUserId,
    sessions,
    setSessions,
    createSession,
    setPlan,
    setTodos,
    setMemories,
  } = useDeepAgent();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<string[]>([]);

  useEffect(() => {
    getSessions(userId)
      .then((items) => {
        if (items.length === 0) return;
        const merged = Array.from(new Set([...items, ...sessions]));
        setSessions(merged);
        if (!merged.includes(threadId)) {
          setThreadId(merged[0]);
        }
      })
      .catch(() => undefined);
  }, [userId]);

  async function send() {
    if (!input.trim()) return;
    setMessages((m) => [...m, `You: ${input}`]);
    try {
      const res = await chat(threadId, userId, input);
      setMessages((m) => [...m, `Agent: ${res.reply}`]);
      if (res.thread_id && res.thread_id !== threadId) {
        setThreadId(res.thread_id);
        if (!sessions.includes(res.thread_id)) {
          setSessions([res.thread_id, ...sessions]);
        }
      }
      setPlan(res.plan);
      setTodos(res.todos);
      setMemories(res.memories);
      setInput("");
    } catch (e: any) {
      setMessages((m) => [...m, `Error: ${e.message}`]);
    }
  }

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Select
          size="small"
          value={threadId}
          onChange={(e) => setThreadId(String(e.target.value))}
          fullWidth
        >
          {sessions.map((id) => (
            <MenuItem key={id} value={id}>
              {id}
            </MenuItem>
          ))}
        </Select>
        <Button variant="outlined" onClick={() => createSession()}>
          New Session
        </Button>
        <TextField
          size="small"
          label="User ID"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          fullWidth
        />
      </Stack>
      <Paper variant="outlined" sx={{ p: 2, minHeight: 300 }}>
        <Stack spacing={1}>
          {messages.map((m, i) => (
            <Typography key={i} variant="body2">
              {m}
            </Typography>
          ))}
        </Stack>
      </Paper>
      <Box display="flex" gap={1}>
        <TextField
          fullWidth
          placeholder="Ask DeepAgent..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
        />
        <Button variant="contained" onClick={send}>
          Send
        </Button>
      </Box>
    </Stack>
  );
}
