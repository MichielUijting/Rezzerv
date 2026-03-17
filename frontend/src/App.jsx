import AppRouter from "./app/router/AppRouter";
import { getRezzervVersionTag } from "./ui/version";

export default function App() {
  const buildTag = getRezzervVersionTag();
  return (
    <>
      <AppRouter />
      <div className="rz-buildtag" aria-hidden="true" data-testid="build-tag">Rezzerv v{buildTag}</div>
    </>
  );
}
