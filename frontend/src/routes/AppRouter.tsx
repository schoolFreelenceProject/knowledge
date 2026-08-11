import { Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { AnalyticsPage } from "../pages/AnalyticsPage";
import { CodeRepositoriesPage } from "../pages/CodeRepositoriesPage";
import { DashboardPage } from "../pages/DashboardPage";
import { DocumentsPage } from "../pages/DocumentsPage";
import { FeedbackPage } from "../pages/FeedbackPage";
import { KnowledgeExplorerPage } from "../pages/KnowledgeExplorerPage";
import { LoginPage } from "../pages/LoginPage";
import { TracesPage } from "../pages/TracesPage";
import { UsersPage } from "../pages/UsersPage";
import { UsersPermissionsPage } from "../pages/UsersPermissionsPage";
import { ProtectedRoute } from "./ProtectedRoute";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/knowledge-explorer" element={<KnowledgeExplorerPage />} />
          <Route path="/code-repositories" element={<CodeRepositoriesPage />} />
          <Route path="/users" element={<UsersPage />} />
          <Route path="/users-permissions" element={<UsersPermissionsPage />} />
          <Route path="/traces" element={<TracesPage />} />
          <Route path="/feedback" element={<FeedbackPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
