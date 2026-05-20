import { ReactNode } from "react";

type HoverGuideProps = {
  text: string;
  children: ReactNode;
  className?: string;
  align?: "left" | "center" | "right";
  side?: "top" | "bottom";
};

export default function HoverGuide({
  text,
  children,
  className,
  align = "center",
  side = "top",
}: HoverGuideProps) {
  const rootClassName = className ? `hover-guide ${className}` : "hover-guide";

  return (
    <div className={rootClassName} data-guide-align={align} data-guide-side={side}>
      {children}
      <span className="hover-guide-bubble" role="tooltip" aria-hidden="true">
        {text}
      </span>
    </div>
  );
}