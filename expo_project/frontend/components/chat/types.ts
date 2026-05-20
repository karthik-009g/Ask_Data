export type AssistantResponseType = "info" | "action" | "error" | "redirect";

export type AssistantResponse = {
  type: AssistantResponseType;
  message: string;
  data: Record<string, unknown>;
  next_steps: string[];
};

export type ChatRole = "user" | "bot";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  responseType?: AssistantResponseType;
  nextSteps?: string[];
  assistantData?: Record<string, unknown>;
};
