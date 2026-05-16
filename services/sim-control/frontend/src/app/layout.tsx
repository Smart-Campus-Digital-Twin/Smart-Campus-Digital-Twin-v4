import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Sim-Control | Sensor Management',
  description: 'Manage and control virtual sensor nodes',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
