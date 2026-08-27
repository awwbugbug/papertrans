export type ProviderName = "mock" | "deepseek" | "kimi" | "zhipu" | "compatible";

export type SourceDocument = {
  id: string;
  path: string;
  name: string;
  size: number;
  pageCount?: number;
};

export type SystemInfo = {
  providers: Array<{
    name: ProviderName;
    label: string;
    defaultModel: string | null;
    requiresApiKey: boolean;
  }>;
  ocr: {
    ready: boolean;
    modelDir: string | null;
  };
  defaultOutputDir: string;
};

export type JobState = {
  id: string;
  status: "queued" | "running" | "completed" | "review" | "failed";
  stage: string;
  sourceName: string;
  provider: ProviderName;
  message: string;
  createdAt: string;
  outputAvailable: boolean;
  report?: {
    passed: boolean;
    pages?: number;
    overflowCount?: number;
    overlapCount?: number;
    minimumFontSize?: number;
  };
};

export type PdfBox = [number, number, number, number];

export type ReadingParagraph = {
  id: string;
  type: string;
  readingOrder: number;
  sourceText: string;
  translation: string;
  sourcePageNumbers: number[];
  translationPageNumbers: number[];
  sourceBoxes: PdfBox[];
  translationBoxes: PdfBox[];
};

export type PageReadingMap = {
  schemaVersion: "m7_reading_map_v1";
  page: {
    number: number;
    width: number;
    height: number;
  };
  paragraphs: ReadingParagraph[];
};

export type PdfTextSelection = {
  flowId: string;
  side: "source" | "translation";
  text: string;
};

export type TextTranslationResult = {
  translation: string;
  compactTranslation: string | null;
  provider: ProviderName;
  characterCount: number;
  protection: {
    tokenCount: number;
    passed: boolean;
  };
  providerExecution: {
    request_count: number;
    cache_hits: number;
    provider_calls: number;
    retry_count: number;
    failure_count: number;
  };
  task: LibraryTaskSummary;
};

export type SelectionTranslationResult = Omit<TextTranslationResult, "task"> & {
  schema: "m7_selection_translation_v1";
};

export type LibraryTaskSummary = {
  id: string;
  kind: "pdf" | "text";
  title: string;
  provider: ProviderName;
  status: "queued" | "running" | "completed" | "review" | "failed";
  message: string;
  createdAt: string;
  updatedAt: string;
  characterCount?: number;
  preview?: string;
};

export type LibraryTaskDetail = LibraryTaskSummary & {
  sourceText?: string;
  translation?: string;
  sourcePath?: string;
  outputDir?: string;
  outputPdf?: string | null;
};

export type StorageUsage = {
  fileCount: number;
  bytes: number;
};

export type StorageInfo = {
  cache: StorageUsage;
  temporaryUploads: StorageUsage;
};

export type StorageCleanupResult = {
  cleared: boolean;
  removed: StorageUsage;
  storage: StorageInfo;
};
