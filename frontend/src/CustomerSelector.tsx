import { useEffect, useMemo, useState } from "react";

import { listProjects } from "./api/projects";
import type { ProjectOption } from "./api/projects";

type CustomerSelectorProps = {
  projectId: string;
  onProjectIdChange: (projectId: string) => void;
  onProjectChange?: (project: ProjectOption | null) => void;
  label?: string;
};

function CustomerSelector({
  projectId,
  onProjectIdChange,
  onProjectChange,
  label = "Customer",
}: CustomerSelectorProps) {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    listProjects()
      .then((nextProjects) => {
        if (!isMounted) {
          return;
        }
        setProjects(nextProjects);
        if (!projectId && nextProjects.length === 1) {
          onProjectIdChange(nextProjects[0].id);
        }
      })
      .catch((requestError) => {
        if (isMounted) {
          setError(requestError instanceof Error ? requestError.message : "Unable to load customers");
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [onProjectIdChange, projectId]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId),
    [projectId, projects]
  );

  useEffect(() => {
    onProjectChange?.(selectedProject ?? null);
  }, [onProjectChange, selectedProject]);

  return (
    <label>
      <span>{label}</span>
      <select
        value={projectId}
        onChange={(event) => onProjectIdChange(event.target.value)}
        disabled={isLoading}
      >
        <option value="">{isLoading ? "Loading customers..." : "Select customer"}</option>
        {projects.map((project) => (
          <option key={project.id} value={project.id}>
            {project.customer_name} - {project.name}
          </option>
        ))}
      </select>
      {selectedProject ? (
        <span className="helper-text">Project ID: {selectedProject.id}</span>
      ) : null}
      {error ? <span className="helper-text error-inline">{error}</span> : null}
    </label>
  );
}

export default CustomerSelector;
