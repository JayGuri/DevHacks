import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import ClickSpark from "@/components/ui/ClickSpark";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <BrowserRouter>
        <TooltipProvider delayDuration={300}>
          <AuthProvider>
            <ClickSpark
              sparkColor='#fff'
              sparkSize={10}
              sparkRadius={15}
              sparkCount={8}
              duration={400}
            >
              <App />
            </ClickSpark>
          </AuthProvider>
        </TooltipProvider>
        <Toaster richColors position="bottom-right" />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
