import AppRouter from "./app/router/AppRouter.jsx";
import { AppFeedbackProvider } from "./ui/AppFeedbackProvider.jsx";
import "./ui/feedback-bar.css";

export default function App() {
  return (
    <AppFeedbackProvider>
      <AppRouter />
      <div
        className="rz-app-feedback-bar-base"
        data-testid="app-feedback-bar-base"
        aria-hidden="true"
      />
    </AppFeedbackProvider>
  );
}
