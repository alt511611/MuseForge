import "../../globals.css";

/**
 * Fourth root layout, and the smallest one on purpose.
 *
 * The embed is somebody else's page's furniture. No Navbar, no AuthProvider,
 * no cookie banner: a consent dialog inside a 405px iframe on a third-party
 * site is a dark pattern, and the page sets no cookies and reads no session, so
 * there is nothing to consent to. No LanguageProvider either — the only words
 * on it are the film's own title and a four-word attribution link.
 *
 * Framing is allowed by `Content-Security-Policy: frame-ancestors *` in
 * next.config.js, which also marks the route noindex: it is the same film as
 * /s/{slug} with the page stripped off, and indexing both asks Google to pick
 * a canonical between a page and a bare player.
 */
export const metadata = {
  robots: { index: false, follow: true },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#000000",
  colorScheme: "dark",
};

export default function EmbedLayout({ children }) {
  return (
    <html lang="en" dir="ltr">
      <body className="antialiased" style={{ margin: 0, backgroundColor: "#000" }}>
        {children}
      </body>
    </html>
  );
}
