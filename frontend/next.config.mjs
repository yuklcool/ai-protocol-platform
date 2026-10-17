/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_BACKEND_URL: process.env.NEXT_PUBLIC_BACKEND_URL,
  },
  async redirects() {
    return [
      { source: '/agents', destination: '/agent', permanent: true },
      { source: '/agents/:agentId', destination: '/agent', permanent: true },
      { source: '/skills/new', destination: '/skills/studio/new', permanent: true },
      { source: '/dev/file-browser', destination: '/agent', permanent: true },
      { source: '/dev/rich-media', destination: '/', permanent: true },
      { source: '/workshop', destination: 'https://github.com/yuklcool/ai-protocol-platform/blob/main/SELFHOST.md', permanent: true },
    ]
  },
  // G45 / Sprint A2A-INVOKE — Friction 25: Next.js's catch-all 404s every
  // `/a2a/*` request before FastAPI ever sees it. Forward them to the
  // backend sidecar so peers can POST JSON-RPC to the A2A invocation
  // surface mounted at /a2a (see backend/protocols/a2a_invocation.py).
  async rewrites() {
    const backend = process.env.BACKEND_URL || 'http://127.0.0.1:1956'
    return [
      { source: '/a2a',        destination: `${backend}/a2a/` },
      { source: '/a2a/:path*', destination: `${backend}/a2a/:path*` },
    ]
  },
}

export default nextConfig
