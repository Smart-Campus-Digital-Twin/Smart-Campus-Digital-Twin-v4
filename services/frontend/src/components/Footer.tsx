"use client";

export default function Footer() {
  return (
    <footer
      style={{
        width: "100%",
        padding: "1.25rem clamp(1rem, 4vw, 2rem)",
        background: "#071952",
        borderTop: "1px solid rgba(151, 254, 237, 0.2)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "0.5rem",
        color: "rgba(151, 254, 237, 0.6)",
        fontSize: "0.8rem",
        marginTop: "auto",
        textAlign: "center",
      }}
    >
      <p>© 2026 University of Moratuwa - Smart Campus Digital Twin</p>
      <p style={{ fontSize: "0.7rem", opacity: 0.8 }}>
        Group I3 • Advanced System Engineering Project
      </p>
    </footer>
  );
}
