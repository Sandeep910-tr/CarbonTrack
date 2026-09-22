import { motion } from "framer-motion";

export default function RouteVisual({ className = "" }) {
  const path = "M 20 260 C 120 260, 100 120, 220 120 S 320 60, 420 90 S 520 220, 620 180";

  const nodes = [
    { x: 20, y: 260, label: "Warehouse" },
    { x: 220, y: 120, label: "Checkpoint" },
    { x: 420, y: 90, label: "Weigh Station" },
    { x: 620, y: 180, label: "Destination" },
  ];

  return (
    <div className={`relative ${className}`}>
      <svg viewBox="0 0 660 320" className="w-full h-auto" fill="none">
        <path d={path} stroke="url(#routeGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.35" />
        <path d={path} stroke="#F0B429" strokeWidth="2.5" strokeLinecap="round" className="route-dash" opacity="0.9" />

        <defs>
          <linearGradient id="routeGrad" x1="0" y1="0" x2="660" y2="0">
            <stop offset="0%" stopColor="#6E6BFF" />
            <stop offset="100%" stopColor="#F0B429" />
          </linearGradient>
        </defs>

        {nodes.map((n, i) => (
          <g key={i}>
            <motion.circle
              cx={n.x} cy={n.y} r="5"
              fill={i === nodes.length - 1 ? "#F0B429" : "#6E6BFF"}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.3 + i * 0.15, duration: 0.4 }}
            />
            <motion.circle
              cx={n.x} cy={n.y} r="10"
              fill="none" stroke={i === nodes.length - 1 ? "#F0B429" : "#6E6BFF"}
              strokeWidth="1"
              initial={{ scale: 0, opacity: 0.6 }}
              animate={{ scale: [1, 2.2], opacity: [0.5, 0] }}
              transition={{ delay: 0.6 + i * 0.15, duration: 1.8, repeat: Infinity, repeatDelay: 1 }}
            />
            <text x={n.x} y={n.y - 16} textAnchor="middle" className="fill-ink-dim" fontSize="10" fontFamily="Inter">
              {n.label}
            </text>
          </g>
        ))}

        {/* moving pulse dot along the route */}
        <motion.circle r="4" fill="#fff">
          <animateMotion dur="3.2s" repeatCount="indefinite" path={path} />
        </motion.circle>
      </svg>
    </div>
  );
}
