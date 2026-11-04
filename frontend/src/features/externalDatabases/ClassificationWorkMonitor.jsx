import Button from '../../ui/Button'

const AREAS = [
  { key: 'identity', title: 'Identificeren' },
  { key: 'classify', title: 'Classificeren' },
  { key: 'synonyms', title: 'Synoniemen' },
]

export default function ClassificationWorkMonitor({ activeArea, onAreaChange }) {
  return <nav aria-label="Artikelbeheer: werkgebieden" data-testid="classification-work-monitor">
    <div className="rz-article-management-areas">
      {AREAS.map((area) => <Button key={area.key} type="button"
        variant={area.key === activeArea ? 'primary' : 'secondary'}
        aria-pressed={area.key === activeArea}
        onClick={() => onAreaChange(area.key)}>
        {area.title}
      </Button>)}
    </div>
  </nav>
}
