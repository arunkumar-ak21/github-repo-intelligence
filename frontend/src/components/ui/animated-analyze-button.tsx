"use client"

import React, { useEffect, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import { Check, Loader2, SendHorizontal, X } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button, ButtonProps } from "@/components/ui/button"

const ANIMATION_CONFIG = {
  spring: {
    type: "spring" as const,
    stiffness: 400,
    damping: 40,
    mass: 0.8,
  },
}

export type AnimatedAnalyzeButtonProps = ButtonProps & {
  status: "idle" | "loading" | "success" | "error"
}

export const AnimatedAnalyzeButton = React.forwardRef<HTMLButtonElement, AnimatedAnalyzeButtonProps>(
  ({ status, className, ...props }, ref) => {
    const [internalState, setInternalState] = useState<"idle" | "sliding" | "loading" | "success" | "error">("idle")

    useEffect(() => {
      if (status === "loading" && internalState === "idle") {
        setInternalState("sliding")
        const timer = setTimeout(() => {
          setInternalState("loading")
        }, 400) // wait for slide animation to finish
        return () => clearTimeout(timer)
      } else if (status !== "loading" && internalState !== "idle" && internalState !== "sliding") {
        setInternalState(status)
      } else if (status === "idle" && internalState !== "idle") {
        setInternalState("idle")
      }
    }, [status, internalState])

    const isShrunk = internalState === "loading" || internalState === "success" || internalState === "error"
    const isSliding = internalState === "sliding"

    return (
      <motion.div
        animate={isShrunk ? { width: "40px" } : { width: "130px" }}
        initial={{ width: "130px" }}
        transition={ANIMATION_CONFIG.spring}
        className={cn("relative flex h-10 items-center justify-center rounded-full bg-zinc-100 m-1 overflow-hidden", className)}
      >
        {/* Expanding black background */}
        <motion.div
          initial={{ width: "40px" }}
          animate={{ width: isSliding || isShrunk ? "100%" : "40px" }}
          transition={ANIMATION_CONFIG.spring}
          className="absolute inset-y-0 left-0 z-0 rounded-full bg-zinc-900"
        />

        {/* Text inside the track */}
        <AnimatePresence>
          {!isShrunk && !isSliding && (
            <motion.div
              initial={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 z-10 flex items-center justify-center pl-6 text-sm font-semibold text-zinc-600"
            >
              Analyze
            </motion.div>
          )}
        </AnimatePresence>

        {/* The sliding arrow circle */}
        <AnimatePresence>
          {!isShrunk && (
            <motion.div
              initial={{ x: 0, opacity: 1 }}
              animate={{ x: isSliding ? 90 : 0, opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={ANIMATION_CONFIG.spring}
              className="absolute left-0 z-20 flex h-full items-center justify-center"
            >
              <div className="flex size-10 items-center justify-center rounded-full bg-zinc-900 text-white shadow-md">
                <SendHorizontal className="size-4" />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* The invisible clickable button covering everything */}
        <Button
          ref={ref}
          type="submit"
          disabled={status !== "idle" || props.disabled}
          {...props}
          className="absolute inset-0 z-30 size-full cursor-pointer rounded-full opacity-0"
        />

        {/* Status icons that appear after it shrinks */}
        <AnimatePresence mode="wait">
          {isShrunk && (
            <motion.div
              className={cn(
                "absolute inset-0 z-40 flex items-center justify-center rounded-full text-white",
                internalState === "success" && "bg-emerald-600",
                internalState === "error" && "bg-red-600",
                internalState === "loading" && "bg-zinc-900"
              )}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.5 }}
            >
              {internalState === "loading" && <Loader2 className="animate-spin size-4" />}
              {internalState === "success" && <Check className="size-4" />}
              {internalState === "error" && <X className="size-4" />}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    )
  }
)

AnimatedAnalyzeButton.displayName = "AnimatedAnalyzeButton"
