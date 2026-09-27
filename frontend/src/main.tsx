// The faces travel with the application, so a page loads nothing from any other site; Open Sans
// stands in for Segoe UI under the OpenMPT theme on systems without it.
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "@fontsource/jetbrains-mono/700.css";
import "@fontsource/open-sans/400.css";
import "@fontsource/open-sans/600.css";
import "@fontsource/open-sans/700.css";
import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/public-sans/700.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const rootElement = document.getElementById("root");
if (rootElement === null) {
    throw new Error("root element not found");
}

createRoot(rootElement).render(
    <StrictMode>
        <App />
    </StrictMode>,
);
