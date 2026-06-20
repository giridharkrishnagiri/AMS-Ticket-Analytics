import { requestJson } from "./client";

export type ProjectOption = {
  id: string;
  name: string;
  code: string;
  client_id: string;
  customer_name: string;
  customer_code: string;
  label: string;
};

export function listProjects(): Promise<ProjectOption[]> {
  return requestJson<ProjectOption[]>("/projects");
}
