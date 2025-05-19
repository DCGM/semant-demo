// TypeScript interfaces generated from Python Pydantic models

export interface SearchRequest {
  query: string;
  limit?: number;
  min_year?: number | null;
  max_year?: number | null;
  min_date?: string | null; // ISO datetime string
  max_date?: string | null; // ISO datetime string
  language?: string | null;
}

export interface Document {
  id: string; // UUID as string
  library: string;
  title: string;
  subtitle?: string | null;
  partNumber?: number | null;
  partName?: string | null;
  yearIssued?: number | null;
  dateIssued?: string | null; // ISO datetime string
  author?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  url?: string | null;
  public?: string | null;
  documentType?: string | null;
  genre?: string | null;
  placeTerm?: string | null;
}

export interface TextChunk {
  id: string; // UUID as string
  title: string;
  text: string;
  start_page_id: string; // UUID as string
  from_page: number;
  to_page: number;
  end_paragraph: boolean;
  language?: string | null;
  document: string; // UUID as string

   ner_P?: string[] | null; // Person entities
  ner_T?: string[] | null; // Temporal entities
  ner_A?: string[] | null; // Address entities
  ner_G?: string[] | null; // Geographical entities
  ner_I?: string[] | null; // Institution entities
  ner_M?: string[] | null; // Media entities
  ner_O?: string[] | null; // Cultural artifacts

}

export interface TextChunkWithDocument extends TextChunk {
  summary?: string | null;
  document_object: Document;
  query_title: string | null;
  query_summary: string | null;
}

export interface SearchResponse {
  results: TextChunkWithDocument[];
  search_request: SearchRequest;
  time_spent: number;
  search_log: string[];
}

export interface SummaryResponse {
  summary: string;
  time_spent: number;
}
