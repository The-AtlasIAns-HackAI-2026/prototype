import { Activity, Home, PhoneCall } from "lucide-react";
import { useState } from "react";
import Analytics from "./Analytics.jsx";
import Demo from "./Demo.jsx";
import Landing from "./Landing.jsx";

const tabs = [
  { id: "landing", label: "الرئيسية", icon: Home },
  { id: "analytics", label: "Analytics", icon: Activity },
  { id: "demo", label: "Demo", icon: PhoneCall },
];

export default function App() {
  const [active, setActive] = useState("landing");
  const ActiveView =
    active === "analytics" ? Analytics : active === "demo" ? Demo : Landing;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" dir="ltr">
          <span className="brand-mark">M</span>
          <span>Moulcyber</span>
        </div>
        <nav className="tabs" aria-label="Views">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                type="button"
                className={active === tab.id ? "tab active" : "tab"}
                onClick={() => setActive(tab.id)}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </header>
      <main>
        <ActiveView />
      </main>
    </div>
  );
}
