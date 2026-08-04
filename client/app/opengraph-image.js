import { ImageResponse } from "next/og";

/* Root-level OG image: applies to every route that does not define its own.
   Generated at build time, so there is no runtime cost per share. */

export const alt = "MuseForge — Agentic AI Video Studio";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          backgroundColor: "#07070b",
          backgroundImage:
            "radial-gradient(ellipse 70% 60% at 50% 0%, #6d28d955 0%, transparent 70%)",
          color: "#f1f3f8",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "18px",
            fontSize: 30,
            letterSpacing: "0.3em",
            textTransform: "uppercase",
            color: "#b9a5fb",
          }}
        >
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              background: "linear-gradient(135deg,#8b5cf6,#6d28d9)",
            }}
          />
          MuseForge
        </div>

        {/* Satori needs an explicit display on any element with >1 child, so
            each headline line is its own block inside a flex column. */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginTop: 36,
            fontSize: 74,
            fontWeight: 700,
            lineHeight: 1.15,
            letterSpacing: "-0.02em",
          }}
        >
          <div>Turn a text idea into a</div>
          <div>cinematic AI video.</div>
        </div>

        <div style={{ marginTop: 32, fontSize: 30, color: "#a8b0c2" }}>
          Script → storyboard → frames → film. In minutes.
        </div>
      </div>
    ),
    size
  );
}
