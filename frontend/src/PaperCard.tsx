import { useState } from 'react'
import type { Paper } from './types'
import PaperModal from './PaperModal'

const SOURCE_LABEL: Record<string, string> = {
  'sci-net': 'On sci-net',
  'sci-hub': 'On sci-hub',
  'not-found': 'Not found',
  'not-checked': 'Not checked',
  pending: 'Pending',
}

function badgeClass(source: string | undefined): string {
  return source && source in SOURCE_LABEL ? source : 'pending'
}

function PaperCard({ paper }: { paper: Paper }) {
  const [open, setOpen] = useState(false)
  const source = paper.source ?? 'pending'
  const href = paper.pdf_link

  return (
    <>
      <article className="card" onClick={() => setOpen(true)}>
        <div className="card-head">
          <h3 className="card-title">{paper.title || 'Untitled paper'}</h3>
          {paper.uploaded && <span className="upload-tag">Newly upload</span>}
        </div>

        {paper.authors && <p className="card-authors">{paper.authors}</p>}

        {paper.journal && (
          <p className="card-journal">
            {paper.journal}
            {paper.year ? ` (${paper.year})` : ''}
          </p>
        )}

        <p className="card-doi">
          <span className="doi-label">DOI</span>
          <span className="doi-value">{paper.doi || '—'}</span>
        </p>

        {paper.topics && paper.topics.length > 0 && (
          <ul className="topics">
            {paper.topics.slice(0, 5).map((topic) => (
              <li key={topic}>{topic}</li>
            ))}
          </ul>
        )}

        {paper.abstract && <p className="card-abstract-preview">{paper.abstract}</p>}

        <div className="card-footer">
          <span className={`badge ${badgeClass(source)}`}>
            {SOURCE_LABEL[source] ?? 'Pending'}
          </span>
          <span className="details-hint">Click for details</span>
        </div>
      </article>

      {open && <PaperModal paper={paper} onClose={() => setOpen(false)} />}
    </>
  )
}

export default PaperCard