// A template re-mounts on every navigation, so each screen eases in.
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="animate-page-in">{children}</div>;
}
