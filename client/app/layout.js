import "../globals.css";

export const metadata = {
  title: "MuseForge — Agentic AI Video Studio",
  description: "Turn ideas into cinematic micro-dramas with multi-agent AI pipeline",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
