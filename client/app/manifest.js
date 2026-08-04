export default function manifest() {
  return {
    name: "MuseForge — Agentic AI Video Studio",
    short_name: "MuseForge",
    description:
      "Turn a text idea into a cinematic micro-drama with a multi-agent AI pipeline.",
    start_url: "/",
    display: "standalone",
    background_color: "#07070b",
    theme_color: "#8b5cf6",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
