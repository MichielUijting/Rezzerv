
import { useParams } from "react-router-dom";
import AppShell from "../../app/AppShell";
import ScreenCard from "../../ui/ScreenCard";
import Tabs from "../../ui/Tabs";

import ArticleOverviewTab from "./tabs/ArticleOverviewTab";
import ArticleStockTab from "./tabs/ArticleStockTab";
import ArticleLocationsTab from "./tabs/ArticleLocationsTab";
import ArticleProductTab from "./tabs/ArticleProductTab";
import ArticleSpecsTab from "./tabs/ArticleSpecsTab";
import ArticlePackagingTab from "./tabs/ArticlePackagingTab";
import ArticleStoresTab from "./tabs/ArticleStoresTab";
import ArticleNotesTab from "./tabs/ArticleNotesTab";

import data from "../../demo-articles.json";

export default function ArticlePage(){

 const { articleId } = useParams();
 const article = data.articles.find(a=>String(a.id)===String(articleId)) || data.articles[0];

 const tabs = [
  {label:"Overzicht", component:<ArticleOverviewTab article={article}/>},
  {label:"Voorraad", component:<ArticleStockTab article={article}/>},
  {label:"Locaties", component:<ArticleLocationsTab article={article}/>},
  {label:"Product", component:<ArticleProductTab article={article}/>},
  {label:"Specificaties", component:<ArticleSpecsTab article={article}/>},
  {label:"Verpakking", component:<ArticlePackagingTab article={article}/>},
  {label:"Winkels", component:<ArticleStoresTab article={article}/>},
  {label:"Notities", component:<ArticleNotesTab article={article}/>}
 ]

 return (
  <AppShell title="Artikel details" showExit={false}>
    <ScreenCard fullWidth title={article.name}>
      <Tabs tabs={tabs}/>
    </ScreenCard>
  </AppShell>
 )
}
