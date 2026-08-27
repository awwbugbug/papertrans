import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/geist/500.css";
import "@fontsource/jetbrains-mono/400.css";
import "material-symbols/outlined.css";
import "./styles.css";

const storedTheme = window.localStorage.getItem("papertrans-theme");
document.documentElement.dataset.theme = storedTheme === "dark" ? "dark" : "light";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
