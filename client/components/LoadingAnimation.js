"use client";

import { useEffect, useRef } from "react";

export default function LoadingAnimation({ size = 80, progress = 0, stage = "" }) {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const angleRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = size / 2 - 6;

    const draw = () => {
      ctx.clearRect(0, 0, size, size);

      // Track
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(124,58,237,0.15)";
      ctx.lineWidth = 4;
      ctx.stroke();

      // Progress arc
      if (progress > 0) {
        const start = -Math.PI / 2;
        const end = start + (progress / 100) * Math.PI * 2;
        const grad = ctx.createLinearGradient(0, 0, size, size);
        grad.addColorStop(0, "#7c3aed");
        grad.addColorStop(1, "#a78bfa");
        ctx.beginPath();
        ctx.arc(cx, cy, r, start, end);
        ctx.strokeStyle = grad;
        ctx.lineWidth = 4;
        ctx.lineCap = "round";
        ctx.stroke();
      }

      // Spinning glow dot
      const angle = angleRef.current;
      const dotX = cx + r * Math.cos(angle);
      const dotY = cy + r * Math.sin(angle);

      const grd = ctx.createRadialGradient(dotX, dotY, 0, dotX, dotY, 10);
      grd.addColorStop(0, "rgba(167,139,250,0.9)");
      grd.addColorStop(1, "rgba(167,139,250,0)");
      ctx.beginPath();
      ctx.arc(dotX, dotY, 10, 0, Math.PI * 2);
      ctx.fillStyle = grd;
      ctx.fill();

      ctx.beginPath();
      ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#a78bfa";
      ctx.fill();

      angleRef.current += 0.04;
      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [size, progress]);

  return (
    <div className="flex flex-col items-center gap-3">
      <canvas ref={canvasRef} style={{ borderRadius: "50%" }} />
      {stage && (
        <span className="text-xs animate-pulse" style={{ color: "#7c3aed" }}>
          {stage}
        </span>
      )}
    </div>
  );
}
