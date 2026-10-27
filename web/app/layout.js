import "./globals.css";

export const metadata = {
  title: "Northbean Coffee",
  description: "D2C coffee sales assistant with a memory layer you can see and control.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
