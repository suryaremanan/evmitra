/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
        './src/components/**/*.{js,ts,jsx,tsx,mdx}',
        './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
                mono: ['var(--font-mono)', 'monospace'],
                display: ['var(--font-display)', 'serif'],
            },
            colors: {
                volt: {
                    50: '#f0fdf4',
                    100: '#dcfce7',
                    400: '#4ade80',
                    500: '#22c55e',
                    600: '#16a34a',
                    900: '#052e16',
                },
                amber: {
                    400: '#fbbf24',
                    500: '#f59e0b',
                },
            },
            animation: {
                'fade-up': 'fadeUp 0.4s ease both',
                'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'shimmer': 'shimmer 2s infinite linear',
            },
            keyframes: {
                fadeUp: {
                    from: { opacity: '0', transform: 'translateY(16px)' },
                    to: { opacity: '1', transform: 'translateY(0)' },
                },
                shimmer: {
                    '0%': { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
            },
        },
    },
    plugins: [],
}
