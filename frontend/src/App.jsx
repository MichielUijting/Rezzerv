import AppRouter from "./app/router/AppRouter.jsx";
import { AppFeedbackProvider } from "./ui/AppFeedbackProvider.jsx";

export default function App() {
  return (
    <AppFeedbackProvider>
      <AppRouter />
    </AppFeedbackProvider>
  );
}
