import "../globals.css";
import { AuthProvider } from "../contexts/AuthContext";
import Navbar from "../components/Navbar";
import CookieConsent from "../components/CookieConsent";

export const metadata = {
  title: "MuseForge — Agentic AI Video Studio",
  description: "Transform any idea into a complete cinematic video using a multi-agent AI pipeline.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="tr">
      <body className="antialiased min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
        <AuthProvider>
          <Navbar />
          {children}
          <CookieConsent />
        </AuthProvider>
      </body>
    </html>
  );
}
