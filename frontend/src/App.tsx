import { Outlet } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";

export function App() {
  return (
    <div className="drawer drawer-open">
      <input id="drawer-toggle" type="checkbox" className="drawer-toggle" />
      <div className="drawer-content p-6">
        <Outlet />
      </div>
      <div className="drawer-side">
        <Sidebar />
      </div>
    </div>
  );
}
