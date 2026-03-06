const path = require('path')

/** @type {import('next').NextConfig} */
const nextConfig = {
    outputFileTracingRoot: path.join(__dirname),
    env: {
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080',
    },
}

module.exports = nextConfig
