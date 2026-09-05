import type { ReactElement } from "react";
import { NavLink, Outlet } from "react-router-dom";

export function Layout(): ReactElement {
    return (
        <div className="layout">
            <header>
                <nav>
                    <NavLink to="/modules">Modules</NavLink>
                    <NavLink to="/stats">Stats</NavLink>
                    <NavLink to="/cloud">Cloud</NavLink>
                </nav>
            </header>
            <main>
                <Outlet />
            </main>
        </div>
    );
}
