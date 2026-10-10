import type { NextConfig } from "next";

// Client-rendered app talking to the FastAPI backend (NEXT_PUBLIC_API_URL).
const nextConfig: NextConfig = {
  // The app has its own floating preferences button; Next's dev-only indicator would sit on top of it.
  // Compile and runtime errors are still shown in development.
  devIndicators: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
