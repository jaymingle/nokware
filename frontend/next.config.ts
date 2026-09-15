import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A self-contained server for the Docker image (see Dockerfile and docs/DEPLOYMENT.md).
  output: "standalone",
};

export default nextConfig;
