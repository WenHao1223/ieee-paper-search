import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createJob, getJob, getResults, refreshResults } from './api'
import PaperCard from './PaperCard'
import type { Job, Paper } from './types'
import './App.css'

const STEP = 25
const MIN = STEP
const MAX = 250
const REFRESH_INTERVAL = 15000
const MAX_REFRESHES = 6

function hasNotFound(results: Paper[] | null): boolean {
  return (results ?? []).some((p) => p.source === 'not-found')
}

function phaseText(job: Job): string {
  if (job.status === 'running') {
    switch (job.phase) {
      case 'checking sci-net / sci-hub':
        return 'Checking availability on sci-net.xyz…'
      case 'downloading missing PDFs':
        return 'Downloading PDFs not found on sci-net/sci-hub…'
      case 'registering and uploading PDFs':
        return 'Registering and uploading PDFs to sci-net.xyz…'
      default:
        return 'Searching IEEE Xplore…'
    }
  }
  if (job.status === 'failed') return 'Something went wrong'
  return 'Search finished'
}

function App() {
  const [query, setQuery] = useState('')
  const [count, setCount] = useState(25)
  const [job, setJob] = useState<Job | null>(null)
  const [results, setResults] = useState<Paper[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const refreshCountRef = useRef(0)

  useEffect(() => {
    getResults()
      .then((data) => setResults(data))
      .catch(() => {
        // ignore: results are loaded lazily after a search
      })
  }, [])

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [job?.log])

  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    },
    [],
  )

  async function startSearch(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    refreshCountRef.current = 0
    setError(null)
    setResults(null)
    setJob(null)
    try {
      const created = await createJob(query.trim(), count)
      if (created.error) {
        setError(created.error)
        return
      }
      poll(created.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  function scheduleRefresh(delay: number) {
    timerRef.current = window.setTimeout(async () => {
      try {
        const updated = await refreshResults()
        setResults(updated)
        if (hasNotFound(updated) && refreshCountRef.current < MAX_REFRESHES) {
          refreshCountRef.current += 1
          scheduleRefresh(REFRESH_INTERVAL)
        }
      } catch {
        // ignore transient refresh errors; remain on last known results
      }
    }, delay)
  }

  function poll(id: string) {
    const tick = async () => {
      try {
        const j = await getJob(id)
        setJob(j)
        if (j.status === 'completed' || j.status === 'failed') {
          if (j.results) {
            setResults(j.results)
            if (j.status === 'completed' && hasNotFound(j.results)) {
              scheduleRefresh(REFRESH_INTERVAL)
            }
          }
          return
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
        return
      }
      timerRef.current = window.setTimeout(tick, 1500)
    }
    void tick()
  }

  const counts = { sciNet: 0, sciHub: 0, notFound: 0, other: 0 }
  for (const p of results ?? []) {
    if (p.source === 'sci-net') counts.sciNet += 1
    else if (p.source === 'sci-hub') counts.sciHub += 1
    else if (p.source === 'not-found') counts.notFound += 1
    else counts.other += 1
  }

  return (
    <div className="app">
      <header className="header">
        <h1>IEEE Paper Search</h1>
        <p className="subtitle">
          Search academic papers on IEEE Xplore and get a direct PDF link from
          sci-net or sci-hub when one is available.
        </p>
      </header>

      <form className="search-form" onSubmit={startSearch}>
        <div className="field">
          <label htmlFor="query">Search query</label>
          <input
            id="query"
            type="text"
            placeholder="e.g. deep learning, transformers, edge computing"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="count">Number of documents</label>
          <div className="count-row">
            <input
              id="count"
              type="range"
              min={MIN}
              max={MAX}
              step={STEP}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
            <output>{count}</output>
          </div>
          <p className="hint">
            Select how many papers you need (in steps of 25). Every 25 documents
            equals one page in the IEEE search.
          </p>
        </div>

        <button className="submit" type="submit" disabled={!query.trim()}>
          Search
        </button>
      </form>

      {error && <div className="error">Error: {error}</div>}

      {job && (
        <section className="progress">
          <div className="phase">
            <span className={`phase-dot ${job.status}`} />
            {phaseText(job)}
          </div>
          <div ref={logRef} className="log-box" aria-live="polite">
            {job.log.map((line, i) => (
              <div key={`${job.id}-${i}`}>{line}</div>
            ))}
            {job.log.length === 0 && <div>Starting…</div>}
          </div>
        </section>
      )}

      {results && (
        <section className="results">
          <div className="summary">
            <span className="chip chip-green">
              {counts.sciNet} on sci-net
            </span>
            <span className="chip chip-amber">
              {counts.sciHub} on sci-hub
            </span>
            <span className="chip chip-red">{counts.notFound} not found</span>
          </div>

          <div className="cards">
            {results.map((p) => (
              <PaperCard paper={p} key={p.number || p.doi || p.link} />
            ))}
          </div>
        </section>
      )}

      {!results && !job && (
        <p className="empty">
          No results yet. Enter a query above to search and check PDF
          availability.
        </p>
      )}
    </div>
  )
}

export default App