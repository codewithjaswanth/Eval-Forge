/**
 * In-memory sliding window rate limiter for EvalForge web API.
 * Mitigates denial-of-service and queue flooding on submission endpoints.
 */

interface RateLimitRecord {
  timestamps: number[];
}

export class RateLimiter {
  private requests: Map<string, RateLimitRecord> = new Map();
  private maxRequests: number;
  private windowMs: number;

  constructor(maxRequests: number = 10, windowMs: number = 60_000) {
    this.maxRequests = maxRequests;
    this.windowMs = windowMs;
  }

  public check(identifier: string): { allowed: boolean; remaining: number; resetTimeMs: number } {
    const now = Date.now();
    const windowStart = now - this.windowMs;

    let record = this.requests.get(identifier);
    if (!record) {
      record = { timestamps: [] };
      this.requests.set(identifier, record);
    }

    // Filter out timestamps older than current sliding window
    record.timestamps = record.timestamps.filter((ts) => ts > windowStart);

    if (record.timestamps.length >= this.maxRequests) {
      const oldest = record.timestamps[0];
      const resetTimeMs = oldest + this.windowMs - now;
      return {
        allowed: false,
        remaining: 0,
        resetTimeMs: Math.max(0, resetTimeMs),
      };
    }

    // Record this request
    record.timestamps.push(now);

    return {
      allowed: true,
      remaining: this.maxRequests - record.timestamps.length,
      resetTimeMs: this.windowMs,
    };
  }

  public reset(identifier?: string): void {
    if (identifier) {
      this.requests.delete(identifier);
    } else {
      this.requests.clear();
    }
  }
}

// Global singleton rate limiter: 10 requests per minute per IP
export const globalSubmissionLimiter = new RateLimiter(10, 60_000);
