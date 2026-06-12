import { createBrowserRouter, Navigate } from "react-router-dom";
import { App } from "./App";
import { RunsList } from "./pages/RunsList";
import { RunDetail } from "./pages/RunDetail";
import { Submit } from "./pages/Submit";
import { Artifacts } from "./pages/Artifacts";
import { Robots } from "./pages/Robots";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/runs" replace /> },
      { path: "runs", element: <RunsList /> },
      { path: "runs/:id", element: <RunDetail /> },
      { path: "submit", element: <Submit /> },
      { path: "artifacts", element: <Artifacts /> },
      { path: "robots", element: <Robots /> },
    ],
  },
]);
