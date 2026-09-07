export interface Paper {
  title: string
  number: string
  link: string
  doi: string
  sci_net?: boolean
  sci_hub?: string
  status?: string
  ticket?: string
  uploaded?: boolean
  pdf_link?: string | null
  source?: string
}

export type JobStatus = 'running' | 'completed' | 'failed'

export interface Job {
  id: string
  status: JobStatus
  phase: string
  params: { query: string; count: number }
  log: string[]
  results: Paper[] | null
}