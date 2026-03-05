
import { useParams, useNavigate } from "react-router-dom";
import AppShell from "../../app/AppShell";
import ArticleTabs from "./ArticleTabs";

export default function ArticlePage() {

  const { articleId } = useParams();
  const navigate = useNavigate();

  return (
    <AppShell title={"Artikel details"}>
      <button onClick={() => navigate("/voorraad")}>← Voorraad</button>
      <ArticleTabs articleId={articleId} />
    </AppShell>
  );
}
