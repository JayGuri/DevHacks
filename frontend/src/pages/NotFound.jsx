import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-display text-8xl text-muted-foreground">404</h1>
      <p className="text-lg text-muted-foreground">Page not found.</p>
      <Button onClick={() => navigate("/login")}>Go Home</Button>
    </div>
  );
}
