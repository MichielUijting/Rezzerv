import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Header from '../../ui/Header.jsx'
import Card from '../../ui/Card.jsx'
import './insights.css'

const tabs = ['Overzicht', 'Uitgaven', 'Voorraad', 'Verbruik', 'Prijzen', 'Benchmark']

const benchmarkProfiles = {
  household: {
    label: 'Vergelijkbaar huishouden',
    description: '2 volwassenen + 2 kinderen',
    spend: 548,
    stock: 385,
    visits: 11,
    receipt: 49.82,
  },
  postcode: {
    label: 'Postcodegebied',
    description: 'voldoende grote, geanonimiseerde regiogroep',
    spend: 584,
    stock: 402,
    visits: 12,
    receipt: 47.30,
  },
  age: {
    label: 'Leeftijdscategorie',
    description: '40–49 jaar',
    spend: 563,
    stock: 394,
    visits: 12,
    receipt: 46.90,
  },
}

const prototype = {
  spend: 612,
  spendChange: 7.4,
  stock: 472,
  stockChange: -3.1,
  almostOut: 7,
  saving: 24,
  visits: 14,
  receipt: 43.71,
  categoryDifferences: [
    { label: 'Frisdrank', value: 42 },
    { label: 'Snacks', value: 31 },
    { label: 'Vlees', value: 18 },
    { label: 'Groente', value: -21 },
    { label: 'Fruit', value: -16 },
  ],
  insights: [
    { title: 'Boodschappen +7,4% deze maand', text: 'Je ligt €42 boven vorige maand. De grootste stijging zit in vlees en frisdrank.', tone: 'up' },
    { title: '7 producten binnenkort op', text: 'Melk, koffie en vaatwastabletten hebben de hoogste urgentie.', tone: 'warn' },
    { title: 'Je voorraad is relatief hoog', text: 'Geschatte voorraadwaarde €472; 22,6% boven vergelijkbare huishoudens.', tone: 'neutral' },
    { title: 'Je betaalt relatief weinig', text: 'Voor 31 vergelijkbare producten ligt jouw gemiddelde betaalde prijs circa 7% onder de benchmark.', tone: 'down' },
  ],
}

function euro(value) {
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR' }).format(value)
}

function percent(value) {
  if (value === 0) return '0%'
  return `${value > 0 ? '+' : '−'}${Math.abs(value).toLocaleString('nl-NL', { maximumFractionDigits: 1 })}%`
}

function Delta({ value }) {
  const className = value > 0 ? 'rz-insights-delta rz-insights-delta--up' : value < 0 ? 'rz-insights-delta rz-insights-delta--down' : 'rz-insights-delta'
  return <span className={className}>{percent(value)}</span>
}

function Metric({ title, value, delta, note }) {
  return (
    <Card className="rz-insights-metric">
      <div className="rz-insights-metric-title">{title}</div>
      <div className="rz-insights-metric-row">
        <strong>{value}</strong>
        {typeof delta === 'number' && <Delta value={delta} />}
      </div>
      {note && <div className="rz-insights-note">{note}</div>}
    </Card>
  )
}

function Bars({ rows }) {
  const max = Math.max(...rows.map((row) => Math.abs(row.value)), 1)
  return (
    <div className="rz-insights-bars">
      {rows.map((row) => (
        <div className="rz-insights-bar-row" key={row.label}>
          <div className="rz-insights-bar-label">{row.label}</div>
          <div className="rz-insights-bar-track" aria-label={`${row.label}: ${percent(row.value)}`}>
            <span className={row.value >= 0 ? 'rz-insights-bar rz-insights-bar--up' : 'rz-insights-bar rz-insights-bar--down'} style={{ width: `${Math.max(8, (Math.abs(row.value) / max) * 100)}%` }} />
          </div>
          <div className="rz-insights-bar-value">{percent(row.value)}</div>
        </div>
      ))}
    </div>
  )
}

function ComparisonRow({ label, own, benchmark, formatter = (v) => v }) {
  const difference = benchmark ? ((own - benchmark) / benchmark) * 100 : 0
  return (
    <div className="rz-insights-comparison-row">
      <div>
        <strong>{label}</strong>
        <div className="rz-insights-note">Jij {formatter(own)} · benchmark {formatter(benchmark)}</div>
      </div>
      <Delta value={difference} />
    </div>
  )
}

export default function InsightsPage() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('Overzicht')
  const [benchmarkKey, setBenchmarkKey] = useState('household')
  const benchmark = benchmarkProfiles[benchmarkKey]

  const spendDifference = useMemo(() => ((prototype.spend - benchmark.spend) / benchmark.spend) * 100, [benchmark])

  return (
    <div className="rz-screen rz-insights-screen" data-testid="insights-page">
      <Header title="Inzichten" />
      <div className="rz-content">
        <div className="rz-content-inner rz-insights-inner">
          <div className="rz-insights-toolbar">
            <button className="rz-insights-back" type="button" onClick={() => navigate('/home')}>← Terug</button>
            <span className="rz-insights-prototype">Prototype · voorbeelddata</span>
          </div>

          <Card className="rz-insights-tabs-card">
            <div className="rz-insights-tabs" role="tablist" aria-label="Inzichten">
              {tabs.map((item) => (
                <button key={item} type="button" role="tab" aria-selected={tab === item} className={tab === item ? 'rz-insights-tab rz-insights-tab--active' : 'rz-insights-tab'} onClick={() => setTab(item)}>{item}</button>
              ))}
            </div>
          </Card>

          {tab === 'Overzicht' && (
            <>
              <div className="rz-insights-metric-grid">
                <Metric title="Uitgaven deze maand" value={euro(prototype.spend)} delta={prototype.spendChange} note="t.o.v. vorige maand" />
                <Metric title="Voorraadwaarde" value={euro(prototype.stock)} delta={prototype.stockChange} note="geschat op basis van bekende prijzen" />
                <Metric title="Binnenkort op" value={`${prototype.almostOut} artikelen`} note="hoogste urgentie: melk, koffie, vaatwastabletten" />
                <Metric title="Mogelijke besparing" value={euro(prototype.saving)} note="op basis van bekende eigen prijsverschillen" />
              </div>

              <Card className="rz-insights-section-card">
                <div className="rz-insights-section-heading">
                  <div>
                    <h2>Dit valt op</h2>
                    <p>De belangrijkste afwijkingen uit je eigen ontwikkeling én je benchmark.</p>
                  </div>
                  <button type="button" className="rz-insights-linkbutton" onClick={() => setTab('Benchmark')}>Bekijk benchmark →</button>
                </div>
                <div className="rz-insights-alert-grid">
                  {prototype.insights.map((item) => (
                    <article className={`rz-insights-alert rz-insights-alert--${item.tone}`} key={item.title}>
                      <strong>{item.title}</strong>
                      <span>{item.text}</span>
                    </article>
                  ))}
                </div>
              </Card>

              <Card className="rz-insights-section-card">
                <div className="rz-insights-section-heading">
                  <div>
                    <h2>Jij versus vergelijkbare huishoudens</h2>
                    <p>{benchmarkProfiles.household.description}</p>
                  </div>
                  <Delta value={((prototype.spend - benchmarkProfiles.household.spend) / benchmarkProfiles.household.spend) * 100} />
                </div>
                <ComparisonRow label="Boodschappen per maand" own={prototype.spend} benchmark={benchmarkProfiles.household.spend} formatter={euro} />
                <ComparisonRow label="Voorraadwaarde" own={prototype.stock} benchmark={benchmarkProfiles.household.stock} formatter={euro} />
                <ComparisonRow label="Winkelbezoeken per maand" own={prototype.visits} benchmark={benchmarkProfiles.household.visits} />
              </Card>
            </>
          )}

          {tab === 'Uitgaven' && (
            <Card className="rz-insights-section-card">
              <h2>Waarom zijn mijn boodschappen duurder?</h2>
              <p className="rz-insights-lead">Deze maand {euro(prototype.spend)}. Prototypeverklaring: circa €19 door hogere betaalde prijzen en €23 door een andere hoeveelheid/productmix.</p>
              <Bars rows={[{ label: 'Prijs', value: 4.1 }, { label: 'Hoeveelheid', value: 2.0 }, { label: 'Productmix', value: 1.3 }]} />
            </Card>
          )}

          {tab === 'Voorraad' && (
            <div className="rz-insights-two-column">
              <Card className="rz-insights-section-card">
                <h2>Voorraadprofiel</h2>
                <Metric title="Geschatte voorraadwaarde" value={euro(prototype.stock)} delta={22.6} note="t.o.v. vergelijkbare huishoudens" />
                <Bars rows={[{ label: 'Droge voorraad', value: 34 }, { label: 'Diepvries', value: 18 }, { label: 'Koelkast', value: -7 }]} />
              </Card>
              <Card className="rz-insights-section-card">
                <h2>Mogelijke overvoorraad</h2>
                <p className="rz-insights-lead">Artikelen die opnieuw zijn gekocht terwijl er nog relatief veel voorraad aanwezig was.</p>
                <ul className="rz-insights-list"><li>Pasta · 11 verpakkingen</li><li>Tomatenblokjes · 9 blikken</li><li>Wasmiddel · 5 flessen</li></ul>
              </Card>
            </div>
          )}

          {tab === 'Verbruik' && (
            <Card className="rz-insights-section-card">
              <h2>Wanneer is het op?</h2>
              <div className="rz-insights-consumption-grid">
                {[['Halfvolle melk','2 dagen','0,7 pak/dag'],['Koffie','25 dagen','1 pak/11 dagen'],['Vaatwastabletten','4 dagen','1,2/dag']].map(([name,days,rate]) => <div className="rz-insights-consumption" key={name}><strong>{name}</strong><span className="rz-insights-consumption-days">{days}</span><small>{rate}</small></div>)}
              </div>
            </Card>
          )}

          {tab === 'Prijzen' && (
            <Card className="rz-insights-section-card">
              <h2>Mijn persoonlijke prijsboek</h2>
              <div className="rz-insights-price-table" role="table" aria-label="Persoonlijk prijsboek">
                <div className="rz-insights-price-head" role="row"><span>Winkel</span><span>Laatste</span><span>Gemiddeld</span><span>Laagste</span></div>
                {[['Lidl',1.09,1.07,0.99],['Jumbo',1.19,1.17,1.09],['Albert Heijn',1.25,1.21,1.15]].map(([store,last,avg,low]) => <div className="rz-insights-price-row" role="row" key={store}><span>{store}</span><span>{euro(last)}</span><span>{euro(avg)}</span><span>{euro(low)}</span></div>)}
              </div>
              <p className="rz-insights-callout">Je betaalt dit voorbeeldproduct gemiddeld het goedkoopst bij Lidl.</p>
            </Card>
          )}

          {tab === 'Benchmark' && (
            <>
              <Card className="rz-insights-section-card">
                <div className="rz-insights-section-heading">
                  <div><h2>Benchmark</h2><p>Vergelijk alleen met voldoende grote, geanonimiseerde groepen.</p></div>
                </div>
                <div className="rz-insights-benchmark-switch" role="group" aria-label="Benchmarkgroep">
                  {Object.entries(benchmarkProfiles).map(([key, item]) => <button type="button" key={key} className={benchmarkKey === key ? 'rz-insights-benchmark-option rz-insights-benchmark-option--active' : 'rz-insights-benchmark-option'} onClick={() => setBenchmarkKey(key)}>{item.label}</button>)}
                </div>
                <div className="rz-insights-benchmark-summary">
                  <div><span>Geselecteerde benchmark</span><strong>{benchmark.label}</strong><small>{benchmark.description}</small></div>
                  <div><span>Jouw boodschappen</span><strong>{euro(prototype.spend)}</strong></div>
                  <div><span>Benchmark</span><strong>{euro(benchmark.spend)}</strong></div>
                  <div><span>Verschil</span><strong><Delta value={spendDifference} /></strong></div>
                </div>
              </Card>

              <div className="rz-insights-two-column">
                <Card className="rz-insights-section-card">
                  <h2>Waar wijk jij af?</h2>
                  <Bars rows={prototype.categoryDifferences} />
                  <p className="rz-insights-note">Beschrijvend, niet normatief: meer of minder dan de gekozen benchmark is niet automatisch beter of slechter.</p>
                </Card>
                <Card className="rz-insights-section-card">
                  <h2>Profiel</h2>
                  <ComparisonRow label="Boodschappen per maand" own={prototype.spend} benchmark={benchmark.spend} formatter={euro} />
                  <ComparisonRow label="Voorraadwaarde" own={prototype.stock} benchmark={benchmark.stock} formatter={euro} />
                  <ComparisonRow label="Winkelbezoeken per maand" own={prototype.visits} benchmark={benchmark.visits} />
                  <ComparisonRow label="Gemiddelde kassabon" own={prototype.receipt} benchmark={benchmark.receipt} formatter={euro} />
                </Card>
              </div>

              <Card className="rz-insights-privacy-card">
                <strong>Privacygrens voor benchmarks</strong>
                <span>Rezzerv toont geen benchmark als een groep te klein is om voldoende anonimiteit te bieden. Bij onvoldoende omvang wordt naar een groter aggregatieniveau opgeschaald.</span>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
