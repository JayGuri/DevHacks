import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import App from "./App";
import "./index.css";

import { useStore } from "@/lib/store";
import { MOCK_USERS, MOCK_PROJECTS, generateNodes, generateRoundMetrics } from "@/lib/mockData";

// ── Checkpoint: verify store + mockData load without errors ──
console.log("[ARFL] Store state:", useStore.getState());
console.log("[ARFL] Mock users:", MOCK_USERS);
console.log("[ARFL] Mock projects:", MOCK_PROJECTS);
console.log("[ARFL] Sample nodes:", generateNodes({ numClients: 10 }));
console.log("[ARFL] Sample round metrics:", generateRoundMetrics(5));

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <BrowserRouter>
        <App />
        <Toaster richColors position="bottom-right" />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
