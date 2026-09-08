import { useEffect } from 'react'
import type { Paper } from './types'

const SOURCE_LABEL: Record<string, string> = {
  'sci-net': 'On sci-net',
  'sci-hub': 'On sci-hub',
  'not-found': 'Not found',
  'not-checked': 'Not checked',
  pending: 'Pending',
}

function PaperModal({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  const source = paper.source ?? 'pending'
  const href = paper.pdf_link

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 className="modal-title">{paper.title || 'Untitled paper'}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="modal-meta">
          <div className="modal-line">
            {paper.authors && <p className="modal-authors">{paper.authors}</p>}
            {paper.journal && (
              <p className="modal-journal">
                {paper.journal}
                {paper.year ? ` (${paper.year})` : ''}
              </p>
            )}
          </div>
          <p className="modal-doi">
            DOI:{' '}
            {paper.doi ? (
              <a
                href={`https://doi.org/${paper.doi}`}
                className="doi-link"
                target="_blank"
                rel="noreferrer noopener"
              >
                {paper.doi}
              </a>
            ) : (
              '—'
            )}
          </p>
          {paper.topics && paper.topics.length > 0 && (
            <ul className="topics">
              {paper.topics.map((topic) => (
                <li key={topic}>{topic}</li>
              ))}
            </ul>
          )}
          <span className={`badge ${source in SOURCE_LABEL ? source : 'pending'}`}>
            {SOURCE_LABEL[source] ?? 'Pending'}
            {paper.uploaded ? ' · Newly upload' : ''}
          </span>
        </div>

        <div className="modal-body">
          {paper.abstract && (
            <div className="modal-abstract">
              <h3 className="modal-section-title">Abstract</h3>
              <p className="modal-abstract-body">{paper.abstract}</p>
            </div>
          )}

          <div className="modal-pdf">
            <h3 className="modal-section-title">Paper</h3>
            {href ? (
              <iframe
                className="modal-pdf-frame"
                src={href}
                title="PDF preview"
              />
            ) : (
              <p className="modal-pdf-unavailable">
                No PDF available for this paper.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default PaperModal
