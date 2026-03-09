const path = require('node:path')
const backendApiUrl = (process.env.BACKEND_API_URL || '').replace(/\/$/, '')

/** @type {import('next').NextConfig} */
const nextConfig = {
    outputFileTracingRoot: path.join(__dirname),
    async rewrites() {
        if (!backendApiUrl) {
            return []
        }

        return [
            {
                source: '/api/:path*',
                destination: `${backendApiUrl}/:path*`,
            },
        ]
    },
}

module.exports = nextConfig
