import { Container, CssBaseline, Typography } from "@mui/material";
import Chat from "./components/Chat";
import { DeepAgentProvider } from "./context";

export default function App() {
  return (
    <DeepAgentProvider>
      <>
        <CssBaseline />
        <Container maxWidth="xl" sx={{ mt: 2, height: "100vh", display: "flex", flexDirection: "column" }}>
          <Typography variant="h5" component="h1" gutterBottom sx={{ fontWeight: "bold", color: "primary.main" }}>
            DeepAgent
          </Typography>
          <Chat />
        </Container>
      </>
    </DeepAgentProvider>
  );
}
