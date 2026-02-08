import { Container, CssBaseline, Grid, Typography } from "@mui/material";
import Chat from "./components/Chat";
import TodoPanel from "./components/TodoPanel";
import { DeepAgentProvider } from "./context";

export default function App() {
  return (
    <DeepAgentProvider>
      <>
        <CssBaseline />
        <Container maxWidth="lg" sx={{ mt: 3 }}>
          <Typography variant="h4" gutterBottom>
            DeepAgent
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={8}>
              <Chat />
            </Grid>
            <Grid item xs={12} md={4}>
              <TodoPanel />
            </Grid>
          </Grid>
        </Container>
      </>
    </DeepAgentProvider>
  );
}
