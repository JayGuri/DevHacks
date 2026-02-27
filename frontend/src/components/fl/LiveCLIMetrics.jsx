import React, { useEffect, useState, useRef } from 'react';
import { API_BASE_URL } from '../../lib/config';

export default function LiveCLIMetrics({ projectId, isEmbedded = false }) {
    const [logs, setLogs] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    const bottomRef = useRef(null);

    // Connect to SSE
    useEffect(() => {
        // Generate the base URL for the SSE endpoint.
        // The SSE endpoint is at /telemetry/stream on the main FastAPI app.
        // Ensure we handle URL formation cleanly whether API_BASE_URL has /api suffix or not
        const baseUrl = API_BASE_URL.replace(/\/api\/?$/, "");
        const sseUrl = `${baseUrl}/telemetry/stream`;

        console.log("[LiveCLIMetrics] Connecting to SSE:", sseUrl);
        const eventSource = new EventSource(sseUrl);

        eventSource.onopen = () => {
            setIsConnected(true);
            addLog({
                type: 'system',
                message: 'Connected to FL Telemetry Stream...',
                timestamp: new Date().toISOString()
            });
        };

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                formatAndAddLog(data);
            } catch (err) {
                console.error("Failed to parse SSE message:", err, event.data);
            }
        };

        eventSource.onerror = (err) => {
            console.error("SSE Error:", err);
            setIsConnected(false);
            addLog({
                type: 'error',
                message: 'Connection lost. Reconnecting...',
                timestamp: new Date().toISOString()
            });
        };

        return () => {
            eventSource.close();
        };
    }, []);

    // Format the raw backend events into human readable CLI logs
    const formatAndAddLog = (payload) => {
        if (!payload || !payload.event) return;

        const ts = payload.timestamp || new Date().toISOString();
        const { event, data } = payload;
        let logEntry = null;

        switch (event) {
            case 'client_joined':
                logEntry = {
                    type: 'info',
                    message: `[JOIN] Client connected: ${data.client_id} | Role: ${data.role} | Task: ${data.task}`,
                    timestamp: ts
                };
                break;
            case 'client_left':
                logEntry = {
                    type: 'warning',
                    message: `[DROP] Client disconnected: ${data.client_id}`,
                    timestamp: ts
                };
                break;
            case 'update_received':
                const loss = data.local_loss ? data.local_loss.toFixed(6) : "N/A";
                const eps = data.epsilon ? data.epsilon.toFixed(4) : "N/A";
                const trust = data.trust_score !== undefined && data.trust_score !== null ? data.trust_score.toFixed(4) : "N/A";
                logEntry = {
                    type: 'success',
                    message: `[UPDATE] Node ${data.client_id} | Task: ${data.task} | Round: ${data.round_num} | Loss: ${loss} | Epsilon: ${eps} | Trust: ${trust}`,
                    timestamp: ts
                };
                break;
            case 'aggregation_triggered':
                logEntry = {
                    type: 'highlight',
                    message: `[AGGREGATION] Triggered | Task: ${data.task} | Round: ${data.round} | Updates: ${data.updates_count} | Active: ${data.active_clients} | Strategy: ${data.strategy}`,
                    timestamp: ts
                };
                break;
            case 'round_complete':
                const acc = data.global_accuracy ? data.global_accuracy.toFixed(2) : "N/A";
                logEntry = {
                    type: 'highlight',
                    message: `[ROUND COMPLETE] Task: ${data.task} | Round: ${data.round} | Global Accuracy: ${acc}% | Updates Used: ${data.updates_used}`,
                    timestamp: ts
                };
                break;
            case 'node_flagged':
                logEntry = {
                    type: 'error',
                    message: `[FLAGGED] Node ${data.client_id} was flagged as malicious | Trust: ${data.trust} | Distance: ${data.distance}`,
                    timestamp: ts
                };
                break;
            default:
                // Ignore noise or unknown events
                return;
        }

        if (logEntry) {
            addLog(logEntry);
        }
    };

    const addLog = (entry) => {
        setLogs(prev => {
            const newLogs = [...prev, entry];
            // Keep last 100 messages to prevent memory bloat
            if (newLogs.length > 100) return newLogs.slice(newLogs.length - 100);
            return newLogs;
        });
    };

    // Auto-scroll to bottom on new log
    useEffect(() => {
        if (bottomRef.current) {
            bottomRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [logs]);

    // Styling maps
    const typeColors = {
        system: 'text-indigo-400',
        info: 'text-blue-400',
        success: 'text-emerald-400',
        warning: 'text-amber-400',
        error: 'text-rose-400',
        highlight: 'text-violet-400 font-bold',
    };

    return (
        <div className={`
      flex flex-col bg-slate-950/80 backdrop-blur-xl border border-slate-800 
      rounded-2xl overflow-hidden shadow-2xl
      ${isEmbedded ? 'h-[400px]' : 'h-[600px] w-full max-w-5xl'}
    `}>
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800 bg-slate-900/50">
                <div className="flex items-center gap-2">
                    <div className="flex gap-1.5 mr-2">
                        <div className="w-3 h-3 rounded-full bg-rose-500"></div>
                        <div className="w-3 h-3 rounded-full bg-amber-500"></div>
                        <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                    </div>
                    <h3 className="text-sm font-semibold text-slate-300 font-mono tracking-wider flex items-center gap-2">
                        <span className="text-violet-400">~/</span>
                        Live Telemetry Console
                        {isConnected ? (
                            <span className="flex h-2 w-2 relative ml-1">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                            </span>
                        ) : (
                            <span className="flex h-2 w-2 relative ml-1">
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                            </span>
                        )}
                    </h3>
                </div>
                <div className="text-xs text-slate-500 font-mono">
                    {logs.length} events
                </div>
            </div>

            {/* Terminal Body */}
            <div className="flex-1 p-4 overflow-y-auto font-mono text-sm leading-relaxed scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
                {logs.length === 0 ? (
                    <div className="text-slate-500 italic mt-2">Waiting for telemetry data...</div>
                ) : (
                    logs.map((log, i) => (
                        <div key={i} className="mb-1.5 break-all hover:bg-slate-800/30 px-1 -mx-1 rounded transition-colors duration-150">
                            <span className="text-slate-500 text-xs mr-3 select-none">
                                {new Date(log.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                            <span className={`${typeColors[log.type] || 'text-slate-300'}`}>
                                {log.message}
                            </span>
                        </div>
                    ))
                )}
                <div ref={bottomRef} className="h-2" />
            </div>
        </div>
    );
}
