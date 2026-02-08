import { Chip, Paper, Stack, Typography } from "@mui/material";
import { useDeepAgent } from "../context";

export default function TodoPanel() {
  const { todos, plan, memories } = useDeepAgent();
  return (
    <Stack spacing={2}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6">Plan</Typography>
        <Stack spacing={1} mt={1}>
          {plan.length === 0 && (
            <Typography variant="body2">No plan yet</Typography>
          )}
          {plan.map((step, i) => (
            <Typography key={i} variant="body2">
              {i + 1}. {step}
            </Typography>
          ))}
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6">Todos</Typography>
        <Stack spacing={1} mt={1}>
          {todos.length === 0 && (
            <Typography variant="body2">No todos yet</Typography>
          )}
          {todos.map((todo) => (
            <Stack key={todo.id} direction="row" spacing={1} alignItems="center">
              <Chip label={todo.status} size="small" />
              <Typography variant="body2">{todo.title}</Typography>
            </Stack>
          ))}
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6">Memories</Typography>
        <Stack spacing={1} mt={1}>
          {memories.length === 0 && (
            <Typography variant="body2">No memories yet</Typography>
          )}
          {memories.map((mem, i) => (
            <Typography key={i} variant="body2">
              {JSON.stringify(mem)}
            </Typography>
          ))}
        </Stack>
      </Paper>
    </Stack>
  );
}
