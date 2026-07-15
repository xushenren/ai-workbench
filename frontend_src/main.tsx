import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { bootAccent } from "@/lib/accentTheme";
import { initTheme } from "@/lib/theme";
initTheme();

bootAccent();  // 启动即应用已保存的个人强调色(否则用 Kun 默认)

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
