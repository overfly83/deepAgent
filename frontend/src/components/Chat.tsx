import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Paper,
  Snackbar,
  Stack,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import PersonIcon from "@mui/icons-material/Person";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import PlayCircleFilledWhiteIcon from "@mui/icons-material/PlayCircleFilledWhite";
import ErrorIcon from "@mui/icons-material/Error";
import { chatStream, getSessions } from "../api";
import { useDeepAgent } from "../context";

// Modern styled components (using sx for simplicity)
const ChatBubble = ({ role, content }: { role: "user" | "agent"; content: string }) => {
  const theme = useTheme();
  const isUser = role === "user";
  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        mb: 2,
      }}
    >
      {!isUser && (
        <SmartToyIcon sx={{ mr: 1, mt: 1, color: theme.palette.primary.main }} />
      )}
      <Paper
        elevation={isUser ? 0 : 1}
        sx={{
          p: 2,
          maxWidth: "80%",
          borderRadius: 2,
          bgcolor: isUser ? theme.palette.primary.main : theme.palette.background.paper,
          color: isUser ? "#fff" : theme.palette.text.primary,
          borderTopLeftRadius: !isUser ? 0 : 2,
          borderTopRightRadius: isUser ? 0 : 2,
        }}
      >
        <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
          {content}
        </Typography>
      </Paper>
      {isUser && (
        <PersonIcon sx={{ ml: 1, mt: 1, color: theme.palette.grey[500] }} />
      )}
    </Box>
  );
};

export default function Chat() {
  const {
    threadId,
    userId,
    setThreadId,
    sessions,
    setSessions,
    plan,
    todos,
    memories,
    setPlan,
    setTodos,
  } = useDeepAgent();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: "user" | "agent"; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Error state
  const [errorOpen, setErrorOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [errorSeverity, setErrorSeverity] = useState<"error" | "warning">("error");

  // Debug mode toggle (could be env var or UI toggle)
  const [debugMode, setDebugMode] = useState(
    typeof import.meta !== "undefined" && (import.meta as any).env && (import.meta as any).env.DEV
  );

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!input.trim() || loading) return;

    setMessages((m) => [...m, { role: "user", content: input }]);
    const currentInput = input;
    setInput("");
    setLoading(true);
    setStatusText("Initializing...");

    let currentReply = "";

    try {
      await chatStream(threadId, userId, currentInput, (event) => {
        switch (event.type) {
          case "token":
            currentReply += event.content;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.role === "agent") {
                const newArr = [...prev];
                newArr[newArr.length - 1] = { ...last, content: currentReply };
                return newArr;
              } else {
                return [...prev, { role: "agent", content: currentReply }];
              }
            });
            break;

          case "plan":
            setPlan(event.plan);
            break;

          case "todos":
            console.log("Received todos update:", event.todos);
            setTodos(event.todos);
            break;

          case "status":
            setStatusText(event.content);
            break;

          case "tool_start":
            setStatusText(`Running tool: ${event.tool}...`);
            break;

          case "tool_end":
            setStatusText(`Finished tool: ${event.tool}`);
            break;
            
          case "error":
             // Handle structured error
             setStatusText("");
             setErrorMsg(event.content);
             setErrorSeverity(event.severity || "error");
             setErrorOpen(true);
             // Also add to chat if critical
             if (event.severity === "error") {
                 setMessages((m) => [...m, { role: "agent", content: `❌ Error: ${event.content}` }]);
             }
             break;
        }
      });
    } catch (e: any) {
      setMessages((m) => [...m, { role: "agent", content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
      setStatusText("");
    }
  }

  return (
    <Grid container spacing={2} sx={{ height: "calc(100vh - 100px)" }}>
      {/* Left Panel: Mission Control */}
      <Grid item xs={12} md={4} sx={{ height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
        {/* Plan Section */}
        <Paper
          variant="outlined"
          sx={{
            flex: debugMode ? 2 : 4,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: 2,
            borderColor: "primary.light",
          }}
        >
          <Box sx={{ p: 2, bgcolor: "grey.50", borderBottom: 1, borderColor: "divider" }}>
            <Typography variant="subtitle1" fontWeight="bold" color="primary">
              📋 Execution Plan
            </Typography>
          </Box>
          <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
            {plan.length === 0 ? (
              <Typography variant="body2" color="text.secondary" fontStyle="italic">
                No active plan. Send a request to generate one.
              </Typography>
            ) : (
              <List dense>
                {plan.map((step, i) => (
                  <ListItem key={i} disablePadding sx={{ mb: 1 }}>
                    <Typography variant="body2">
                      <strong>{i + 1}.</strong> {step}
                    </Typography>
                  </ListItem>
                ))}
              </List>
            )}
          </Box>
        </Paper>

        {/* Todos Section */}
        <Paper
          variant="outlined"
          sx={{
            flex: debugMode ? 3 : 6,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: 2,
            borderColor: "secondary.light",
          }}
        >
          <Box sx={{ p: 2, bgcolor: "grey.50", borderBottom: 1, borderColor: "divider" }}>
            <Typography variant="subtitle1" fontWeight="bold" color="secondary">
              ✅ Tasks & Progress
            </Typography>
          </Box>
          <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
            {todos.length === 0 ? (
              <Typography variant="body2" color="text.secondary" fontStyle="italic">
                No tasks pending.
              </Typography>
            ) : (
              <List dense>
                {todos.map((todo) => {
                   let icon = <RadioButtonUncheckedIcon fontSize="small" color="disabled" />;
                   if (todo.status === "in_progress") icon = <PlayCircleFilledWhiteIcon fontSize="small" color="info" />;
                   if (todo.status === "completed" || todo.status === "done") icon = <CheckCircleIcon fontSize="small" color="success" />;
                   if (todo.status === "failed") icon = <ErrorIcon fontSize="small" color="error" />;
                   
                   return (
                    <ListItem key={todo.id} sx={{ borderBottom: "1px dashed #eee" }}>
                      <Box sx={{ mr: 1, display: "flex", alignItems: "center" }}>
                        {icon}
                      </Box>
                      <ListItemText
                        primary={todo.title}
                        primaryTypographyProps={{
                          variant: "body2",
                          style: { textDecoration: todo.status === "completed" ? "line-through" : "none" }
                        }}
                      />
                      <Chip 
                        label={todo.status.replace("_", " ")} 
                        size="small" 
                        color={todo.status === "completed" ? "success" : todo.status === "in_progress" ? "info" : "default"}
                        variant="outlined"
                        sx={{ fontSize: "0.6rem", height: 20, ml: 1 }}
                      />
                    </ListItem>
                   );
                })}
              </List>
            )}
          </Box>
        </Paper>

        {/* Memories Section - Only in Debug Mode */}
        {debugMode && (
        <Paper
          variant="outlined"
          sx={{
            flex: 5,
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: 2,
            borderColor: "info.light",
          }}
        >
          <Box sx={{ p: 2, bgcolor: "grey.50", borderBottom: 1, borderColor: "divider" }}>
            <Typography variant="subtitle1" fontWeight="bold" color="info.main">
              🧠 Core Memory
            </Typography>
          </Box>
          <Box sx={{ p: 2, overflowY: "auto", flex: 1 }}>
            {memories.length === 0 ? (
              <Typography variant="body2" color="text.secondary" fontStyle="italic">
                No memories stored yet.
              </Typography>
            ) : (
              <List dense>
                {memories.map((mem, i) => (
                  <ListItem key={i} disablePadding sx={{ mb: 1 }}>
                    <Paper 
                        elevation={0} 
                        sx={{ 
                            p: 1, 
                            bgcolor: "info.light", 
                            color: "info.contrastText", 
                            borderRadius: 1, 
                            width: "100%",
                            opacity: 0.9
                        }}
                    >
                        <Typography variant="caption" display="block" fontWeight="bold">
                            {(mem.scope as string)?.toUpperCase() || "GLOBAL"}
                        </Typography>
                        <Typography variant="body2">
                            {mem.content || JSON.stringify(mem)}
                        </Typography>
                    </Paper>
                  </ListItem>
                ))}
              </List>
            )}
          </Box>
        </Paper>
        )}
      </Grid>

      {/* Right Panel: Chat Area */}
      <Grid item xs={12} md={8} sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
        {/* Error Snackbar */}
        <Snackbar 
            open={errorOpen} 
            autoHideDuration={6000} 
            onClose={() => setErrorOpen(false)}
            anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
            <Alert onClose={() => setErrorOpen(false)} severity={errorSeverity as any} sx={{ width: '100%' }}>
                {errorMsg}
            </Alert>
        </Snackbar>
        
        <Paper
          variant="elevation"
          elevation={2}
          sx={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          <Box sx={{ p: 2, bgcolor: "primary.main", color: "white" }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6">DeepAgent Chat</Typography>
              {statusText && (
                 <Chip label={statusText} size="small" sx={{ bgcolor: "rgba(255,255,255,0.2)", color: "white" }} />
              )}
            </Stack>
          </Box>
          
          <Box sx={{ p: 2, flex: 1, overflowY: "auto", bgcolor: "grey.50" }}>
            {messages.length === 0 && (
              <Box display="flex" justifyContent="center" alignItems="center" height="100%" flexDirection="column" opacity={0.5}>
                <SmartToyIcon sx={{ fontSize: 60, mb: 2 }} />
                <Typography>How can I help you today?</Typography>
              </Box>
            )}
            {messages.map((m, i) => (
              <ChatBubble key={i} role={m.role} content={m.content} />
            ))}
            <div ref={messagesEndRef} />
          </Box>
          
          <Divider />
          
          <Box sx={{ p: 2, bgcolor: "background.paper" }}>
            <Stack direction="row" spacing={1}>
              <TextField
                fullWidth
                placeholder="Type your request..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                multiline
                maxRows={3}
                size="small"
                sx={{ 
                    "& .MuiOutlinedInput-root": { borderRadius: 3 }
                }}
              />
              <IconButton 
                color="primary" 
                onClick={send} 
                disabled={loading || !input.trim()}
                sx={{ 
                    bgcolor: "primary.main", 
                    color: "white", 
                    "&:hover": { bgcolor: "primary.dark" },
                    "&:disabled": { bgcolor: "grey.300" },
                    width: 40,
                    height: 40,
                }}
              >
                <SendIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Box>
        </Paper>
      </Grid>
    </Grid>
  );
}
