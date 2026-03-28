import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["maplibre-gl"],
  turbopack: {},
  devIndicators: false,
};

export default nextConfig;
