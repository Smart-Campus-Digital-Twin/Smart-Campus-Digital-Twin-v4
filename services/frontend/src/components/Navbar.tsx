"use client";

import Link from "next/link";
import { Building2, LogIn, LogOut, UserPlus } from "lucide-react";
import { useAuth } from "@/components/auth/KeycloakProvider";

export default function Navbar() {
  const { isReady, isAuthenticated, username, login, register, logout } = useAuth();

  return (
    <nav
      style={{
        width: "100%",
        padding: "0.85rem clamp(1rem, 4vw, 2rem)",
        background: "rgba(11, 102, 106, 0.9)",
        backdropFilter: "blur(10px)",
        borderBottom: "1px solid rgba(151, 254, 237, 0.3)",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: "1rem",
        flexWrap: "wrap",
        position: "fixed",
        top: 0,
        zIndex: 20000,
        color: "white",
      }}
    >
      <Link
        href="/"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          textDecoration: "none",
          color: "inherit",
          minWidth: 0,
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "#97FEED",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Building2 color="#071952" size={18} />
        </div>
        <span
          style={{
            fontWeight: 700,
            fontSize: "clamp(1rem, 4vw, 1.2rem)",
            letterSpacing: "-0.5px",
            whiteSpace: "nowrap",
          }}
        >
          UOM<span style={{ color: "#97FEED" }}>Twin</span>
        </span>
      </Link>

      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
        <span
          style={{
            padding: "0.4rem 0.75rem",
            borderRadius: 999,
            border: "1px solid rgba(151, 254, 237, 0.25)",
            background: "rgba(7, 25, 82, 0.35)",
            color: "#97FEED",
            fontSize: "0.75rem",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {isReady ? (isAuthenticated ? username || "Authenticated" : "Signed out") : "Signing in"}
        </span>
        {isAuthenticated ? (
          <button
            onClick={logout}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.65rem 1rem",
              borderRadius: 999,
              border: "1px solid rgba(151, 254, 237, 0.35)",
              background: "rgba(7, 25, 82, 0.55)",
              color: "#97FEED",
              fontSize: "0.8rem",
              fontWeight: 800,
              cursor: "pointer",
            }}
          >
            <LogOut size={14} />
            Sign out
          </button>
        ) : (
          <>
            <button
              onClick={login}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.45rem",
                padding: "0.65rem 1rem",
                borderRadius: 999,
                border: "1px solid rgba(151, 254, 237, 0.35)",
                background: "rgba(7, 25, 82, 0.55)",
                color: "#97FEED",
                fontSize: "0.8rem",
                fontWeight: 800,
                cursor: "pointer",
              }}
            >
              <LogIn size={14} />
              Sign in
            </button>
            <button
              onClick={register}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.45rem",
                padding: "0.65rem 1rem",
                borderRadius: 999,
                border: "1px solid rgba(151, 254, 237, 0.35)",
                background: "linear-gradient(135deg, #97FEED 0%, #35A29F 100%)",
                color: "#071952",
                fontSize: "0.8rem",
                fontWeight: 800,
                cursor: "pointer",
              }}
            >
              <UserPlus size={14} />
              Sign up
            </button>
          </>
        )}
      </div>
    </nav>
  );
}
