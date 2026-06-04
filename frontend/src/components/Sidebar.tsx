import { NavLink } from "react-router-dom";

const links = [
  { to: "/runs", label: "Runs" },
  { to: "/submit", label: "Submit" },
  { to: "/artifacts", label: "Artifacts" },
];

export function Sidebar() {
  return (
    <aside className="bg-base-200 min-h-screen w-56 p-4">
      <h1 className="text-xl font-bold mb-6">Orchestrator</h1>
      <ul className="menu">
        {links.map((l) => (
          <li key={l.to}>
            <NavLink
              to={l.to}
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              {l.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </aside>
  );
}
