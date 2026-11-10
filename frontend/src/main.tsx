import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./app/App";
import { createQueryClient } from "./app/queryClient";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Élément #root introuvable");

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <App client={createQueryClient()} />
    </BrowserRouter>
  </StrictMode>,
);
