/**
 * The embedded player: one video, one attribution link, no chrome.
 *
 * A server component with no interactivity of its own — the <video> element's
 * own controls are the whole UI, so there is no reason to ship a client bundle
 * into an iframe that is sitting on somebody else's page weighing down their
 * Core Web Vitals.
 *
 * The attribution link is the point of the whole route. `target="_blank"` with
 * `rel="noopener"` and NOT `nofollow`: this is a link the embedder chose to
 * place, which is exactly the kind search engines are supposed to count.
 *
 * `preload="metadata"` rather than the share page's `none`: an embed is
 * usually below the fold on someone else's article, and the browser needs the
 * dimensions to avoid a layout shift on their page, not ours.
 */
export default function EmbedPlayer({ src, poster, title, href }) {
  return (
    <div style={{ position: "relative", width: "100%", height: "100vh", background: "#000" }}>
      {src ? (
        <video
          src={src}
          poster={poster || undefined}
          title={title}
          controls
          playsInline
          preload="metadata"
          style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
        />
      ) : (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            height: "100%",
            color: "#9aa0a6",
            font: "14px/1.4 system-ui, sans-serif",
          }}
        >
          This video is no longer available.
        </div>
      )}

      <a
        href={href}
        target="_blank"
        rel="noopener"
        style={{
          position: "absolute",
          right: 10,
          /* Top, not bottom. The browser's own control bar owns the bottom
             ~40px of the frame and is drawn over anything placed there, so an
             attribution link in the corner sat on top of the scrubber -- which
             both hid the link and made the last seconds of the film hard to
             seek to on somebody else's page. */
          top: 10,
          padding: "6px 10px",
          borderRadius: 8,
          background: "rgba(7,7,11,.72)",
          color: "#e7e7ea",
          font: "600 11px/1 system-ui, sans-serif",
          textDecoration: "none",
          letterSpacing: ".02em",
        }}
      >
        Made with MuseForge
      </a>
    </div>
  );
}
