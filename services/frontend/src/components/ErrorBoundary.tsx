"use client";

import React, { ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100vh",
              width: "100%",
              background:
                "radial-gradient(circle at center, #0B666A 0%, #071952 100%)",
              color: "#fff",
              flexDirection: "column",
              gap: "20px",
              fontFamily: "system-ui, sans-serif",
            }}
          >
            <div
              style={{
                textAlign: "center",
                padding: "40px",
                background: "rgba(11, 102, 106, 0.2)",
                border: "1px solid rgba(151, 254, 237, 0.3)",
                borderRadius: "16px",
                backdropFilter: "blur(10px)",
              }}
            >
              <h1
                style={{
                  fontSize: "32px",
                  marginBottom: "16px",
                  color: "#97FEED",
                }}
              >
                Something went wrong
              </h1>
              <p
                style={{ fontSize: "16px", marginBottom: "24px", opacity: 0.8 }}
              >
                {this.state.error?.message || "An unexpected error occurred"}
              </p>
              <button
                onClick={() => window.location.reload()}
                style={{
                  padding: "12px 24px",
                  background:
                    "linear-gradient(135deg, #0B666A 0%, #071952 100%)",
                  color: "#97FEED",
                  border: "1px solid rgba(151, 254, 237, 0.4)",
                  borderRadius: "8px",
                  cursor: "pointer",
                  fontSize: "14px",
                  fontWeight: "bold",
                  transition: "all 0.3s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow =
                    "0 4px 15px rgba(151, 254, 237, 0.3)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = "none";
                }}
              >
                Reload Page
              </button>
            </div>
          </div>
        )
      );
    }

    return this.props.children;
  }
}
