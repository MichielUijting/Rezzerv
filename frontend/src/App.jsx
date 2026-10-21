import MaintenanceNotice from "./features/platform/MaintenanceNotice.jsx";
import AppRouter from "./app/router/AppRouter.jsx";
import { AppFeedbackProvider } from "./ui/AppFeedbackProvider.jsx";
import "./ui/feedback-bar.css";

export default function App() {
  return (
    <AppFeedbackProvider>
      <MaintenanceNotice />
      <AppRouter />
      <div
        data-testid="app-feedback-bar-scroll-clearance"
        aria-hidden="true"
        style={{
          height: 'calc(var(--size-app-bar-mobile) + env(safe-area-inset-bottom))',
          pointerEvents: 'none',
        }}
      />
      <div
        className="rz-app-feedback-bar-base"
        data-testid="app-feedback-bar-base"
        aria-hidden="true"
      />
    </AppFeedbackProvider>
  );
}
