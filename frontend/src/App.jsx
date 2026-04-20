import { useEffect, useState } from "react";
import AppRouter from "./app/router/AppRouter.jsx";
import { getRezzervVersionTag, formatRezzervVersionLabel } from "./ui/version";

export default function App() {
  const [buildTag, setBuildTag] = useState(getRezzervVersionTag());

  useEffect(() => {
    const refreshVersion = () => setBuildTag(getRezzervVersionTag());
    window.addEventListener("rezzerv-version-ready", refreshVersion);
    return () => window.removeEventListener("rezzerv-version-ready", refreshVersion);
  }, []);

  return (
    <>
      <AppRouter />
      <div className="rz-buildtag" aria-hidden="true" data-testid="build-tag">
        {formatRezzervVersionLabel(buildTag)}
      </div>
    </>
  );
}
