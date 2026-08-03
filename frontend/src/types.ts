export type ProviderName = "mock" | "deepseek" | "kimi" | "compatible";

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
