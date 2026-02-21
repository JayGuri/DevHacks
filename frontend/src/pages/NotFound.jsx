import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { memo } from "react";

const NotFound = memo(() => {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background empty-state-bg">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className="metric-value text-muted-foreground/20 text-9xl">404</h1>
        <p className="metric-label mt-4 text-lg">System Navigation Failure</p>
        <p className="text-muted-foreground mt-2 max-w-[300px] text-sm">
          The requested route is not present in the current simulation cluster.
        </p>
        <Button 
          onClick={() => navigate("/")} 
          className="mt-8 rounded-full btn-primary-glow px-8"
        >
          Return to Command
        </Button>
      </motion.div>
    </div>
  );
});

export default NotFound;
