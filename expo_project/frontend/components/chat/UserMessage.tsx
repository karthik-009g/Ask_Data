import { ChatMessage } from "./types";

type UserMessageProps = {
  message: ChatMessage;
};

export default function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[82%] rounded-2xl bg-gradient-to-r from-sky-500 via-cyan-500 to-emerald-500 px-4 py-3 text-sm text-white shadow-[0_10px_24px_rgba(14,165,233,0.28)]">
        {message.text}
      </div>
    </div>
  );
}
