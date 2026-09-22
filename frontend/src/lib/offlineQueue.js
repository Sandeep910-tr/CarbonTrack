// Keeps GPS location pings from being silently lost when a driver has no
// signal (a real scenario for logistics routes through rural/highway
// stretches). Pings that fail to POST are queued in localStorage and
// retried automatically once the browser reports 'online' again.

const QUEUE_KEY = "cfl_offline_ping_queue";

function readQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}

function writeQueue(queue) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
  } catch {
    // storage full or unavailable — nothing more we can do here
  }
}

export function queueSize() {
  return readQueue().length;
}

export function enqueuePing(tripId, payload) {
  const queue = readQueue();
  queue.push({ tripId, payload, queuedAt: Date.now() });
  // Cap the queue so a long offline stretch can't grow this unbounded.
  writeQueue(queue.slice(-200));
}

export async function flushQueue(api, onProgress) {
  const queue = readQueue();
  if (queue.length === 0) return { sent: 0, remaining: 0 };
  let sent = 0;
  const remaining = [];
  for (const item of queue) {
    try {
      await api.post(`/driver/trips/${item.tripId}/location`, item.payload);
      sent += 1;
    } catch {
      remaining.push(item); // still offline or trip no longer accepts pings — keep for next retry
    }
  }
  writeQueue(remaining);
  onProgress?.({ sent, remaining: remaining.length });
  return { sent, remaining: remaining.length };
}
