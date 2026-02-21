import { useRef, useEffect } from "react";
import { useMotionValue, useSpring, useTransform, animate } from "framer-motion";

export default function AnimatedNumber({ value, decimals = 1, prefix = "", suffix = "" }) {
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, {
    damping: 25,
    stiffness: 100,
  });

  const displayValue = useTransform(springValue, (latest) => {
    return `${prefix}${latest.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}${suffix}`;
  });

  const spanRef = useRef(null);

  useEffect(() => {
    animate(motionValue, value, {
      duration: 0.6,
    });
  }, [value, motionValue]);

  useEffect(() => {
    return displayValue.on("change", (latest) => {
      if (spanRef.current) {
        spanRef.current.textContent = latest;
      }
    });
  }, [displayValue]);

  return <span ref={spanRef} />;
}
