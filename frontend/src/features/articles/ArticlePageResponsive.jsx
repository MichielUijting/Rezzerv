import ArticlePage from './ArticlePage.jsx'
import MobileArticlePage from './MobileArticlePage.jsx'
import { useMobileAppViewport } from '../../app/mobileViewport.js'

export default function ArticlePageResponsive() {
  const isMobileViewport = useMobileAppViewport()

  if (isMobileViewport) {
    return <MobileArticlePage />
  }

  return <ArticlePage />
}
