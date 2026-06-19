import { cn } from "@/lib/utils";
import React from "react";

interface AnimatedActionButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  href?: string;
  target?: string;
  rel?: string;
}

export const AnimatedActionButton = ({ children, className, href, target, rel, ...props }: AnimatedActionButtonProps) => {
  const content = (
    <>
      <span className="w-48 h-48 rounded rotate-[-40deg] bg-zinc-900 absolute bottom-0 left-0 -translate-x-full ease-out duration-500 transition-all translate-y-full mb-9 ml-9 group-hover:ml-0 group-hover:mb-32 group-hover:translate-x-0"></span>
      <span className="relative w-full flex items-center justify-center text-zinc-900 transition-colors duration-300 ease-in-out group-hover:text-white">
        {children}
      </span>
    </>
  );

  const baseClassName = cn(
    "relative inline-flex items-center justify-center px-6 py-2 overflow-hidden font-semibold transition-all bg-white/80 backdrop-blur-sm rounded-xl hover:bg-white group outline outline-1 outline-zinc-200/50 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed",
    className
  );

  if (href) {
    return (
      <a href={href} target={target} rel={rel} className={baseClassName}>
        {content}
      </a>
    );
  }

  return (
    <button className={baseClassName} {...props}>
      {content}
    </button>
  );
};
