import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { AuthGate } from "@/components/auth/AuthGate";
import { ThemeProvider } from "@/context/ThemeContext";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: {
    default: "Agent Guardian",
    template: "%s | Agent Guardian",
  },
  description: "Multi-agent codebase auditing powered by Google ADK. High-precision security, quality, governance and architecture command center.",
  openGraph: {
    type: "website",
    title: "Agent Guardian | Mission Control",
    description: "High-precision multi-agent codebase auditing command center powered by Google ADK.",
  },
  robots: {
    index: false,
    follow: false,
  },
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`h-full antialiased dark ${inter.variable} ${jetbrainsMono.variable}`}
      data-theme="dark"
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("ag_theme")||"dark";document.documentElement.setAttribute("data-theme",t);document.documentElement.style.colorScheme=t;if(t==="dark"){document.documentElement.classList.add("dark");document.documentElement.classList.remove("light");}else{document.documentElement.classList.add("light");document.documentElement.classList.remove("dark");}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-screen font-sans selection:bg-[#2525A3]/30 selection:text-white transition-colors duration-200">
        <ThemeProvider>
          <AuthGate>{children}</AuthGate>
        </ThemeProvider>
      </body>
    </html>
  );
}


