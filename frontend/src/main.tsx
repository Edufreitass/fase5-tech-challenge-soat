import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { FalhaInicial } from "./components/InitialFailure";
import { AuthProvider } from "./context/AuthContext";
import { carregarConfig } from "./lib/config";
import "./index.css";

const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("Elemento raiz da aplicação não encontrado.");

carregarConfig()
  .then(() =>
    createRoot(raiz).render(
      <StrictMode>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </StrictMode>,
    ),
  )
  .catch(() => createRoot(raiz).render(<FalhaInicial />));
