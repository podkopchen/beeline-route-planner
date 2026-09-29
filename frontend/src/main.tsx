import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { AuthGate } from "./components/AuthGate";
import "./styles/index.css";
import "./styles/glass.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthGate>{(user, signOut) => <App user={user} onLogout={signOut} />}</AuthGate>
  </StrictMode>,
);
