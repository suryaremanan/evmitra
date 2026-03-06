import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
    title: 'VoltSage — The World\'s Honest EV Advisor',
    description: 'Real data, real owners, real advice. Compare EVs globally with live charging data and honest verdicts powered by AI.',
    keywords: 'electric vehicle, EV advisor, EV comparison, charging stations, global EV',
    openGraph: {
        title: 'VoltSage — The World\'s Honest EV Advisor',
        description: 'Real data, real owners, real advice on EVs anywhere in the world.',
        type: 'website',
    },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="en">
            <body className="antialiased min-h-screen bg-[#07090f]">
                {children}
            </body>
        </html>
    )
}
