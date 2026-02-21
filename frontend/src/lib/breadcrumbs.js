/**
 * Returns an array of { label, href? } breadcrumb objects
 * based on the current pathname, route params, and project list.
 */
export function getBreadcrumbs(pathname, params, projects = []) {
    const { id } = params;

    function findProject(projectId) {
        return projects.find((p) => p.id === projectId);
    }

    // Dashboard routes
    if (pathname === "/dashboard/overview") {
        return [{ label: "Overview" }];
    }
    if (pathname === "/dashboard/projects") {
        return [{ label: "Projects" }];
    }
    if (pathname.startsWith("/dashboard/projects/") && id) {
        const project = findProject(id);
        return [
            { label: "Projects", href: "/dashboard/projects" },
            { label: project?.name || id },
        ];
    }
    if (pathname === "/dashboard/profile") {
        return [{ label: "Profile" }];
    }

    // Admin routes
    if (pathname === "/admin/overview") {
        return [{ label: "System" }];
    }
    if (pathname === "/admin/projects") {
        return [{ label: "Projects" }];
    }
    if (pathname.startsWith("/admin/projects/") && id) {
        const project = findProject(id);
        return [
            { label: "Projects", href: "/admin/projects" },
            { label: project?.name || id },
        ];
    }
    if (pathname === "/admin/users") {
        return [{ label: "Users" }];
    }
    if (pathname === "/admin/requests") {
        return [{ label: "Join Requests" }];
    }
    if (pathname === "/admin/security") {
        return [{ label: "Security" }];
    }

    return [];
}
