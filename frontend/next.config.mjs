/** @type {import('next').NextConfig} */
const nextConfig = {
  // Produces a minimal server bundle for the Docker image.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
