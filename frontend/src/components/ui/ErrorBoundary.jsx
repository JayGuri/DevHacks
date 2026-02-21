import React from "react";
import { Button } from "@/components/ui/button";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("Simulation Runtime Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-background empty-state-bg p-6 text-center">
          <div className="card-elevated max-w-md p-8 bg-card/80 backdrop-blur-xl border-rose-500/20">
            <h2 className="metric-value text-rose-500 text-4xl mb-4">CRITICAL FAILURE</h2>
            <p className="metric-label text-rose-400 mb-6 tracking-widest uppercase">System Execution Halted</p>
            <div className="bg-slate-950/50 p-4 rounded-lg border border-white/5 mb-8 text-left overflow-auto max-h-[150px]">
               <code className="text-rose-300 text-[10px] font-mono whitespace-pre-wrap">
                 {this.state.error?.toString()}
               </code>
            </div>
            <Button 
               onClick={() => window.location.reload()} 
               className="w-full rounded-full bg-rose-600 hover:bg-rose-500 text-white font-mono uppercase tracking-widest text-xs h-12"
            >
              Reinitialize Cluster
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
