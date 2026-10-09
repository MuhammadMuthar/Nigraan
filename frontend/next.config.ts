import type { NextConfig } from "next";

// Client-rendered app talking to the FastAPI backend (NEXT_PUBLIC_API_URL).
const nextConfig: NextConfig = {
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
