import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

const apiUrl = (import.meta.env.VITE_API_URL ?? "").trim();
const explicitDemoMode = import.meta.env.VITE_DEMO_MODE === "true";
const productionMisconfigured = import.meta.env.PROD && !apiUrl && !explicitDemoMode;

function ProductionConfigurationError() {
  return (
    <main className="app-config-error" data-testid="crm-config-error" role="alert">
      <h1>CRM не підключена до API</h1>
      <p>
        Production-збірка запущена без VITE_API_URL. Демонстраційні дані навмисно не показуються,
        щоб їх не можна було сплутати з реальними даними учнів.
      </p>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {productionMisconfigured ? <ProductionConfigurationError /> : <App />}
  </React.StrictMode>,
);
