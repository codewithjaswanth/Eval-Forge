import { z } from "zod";

export const submissionSchema = z.object({
  repoUrl: z
    .string()
    .trim()
    .min(1, "GitHub repository URL is required")
    .regex(
      /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(\/)?$/,
      "Please enter a valid GitHub repository URL (e.g. https://github.com/owner/repo)"
    ),
  liveUrl: z
    .string()
    .trim()
    .url("Live URL must be a valid URL (e.g. https://example.com)")
    .refine((val) => {
      if (!val) return true;
      try {
        const parsed = new URL(val);
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
          return false;
        }
        const host = parsed.hostname.toLowerCase();
        // Disallow localhost, private IPs, and cloud metadata
        if (
          host === "localhost" ||
          host === "127.0.0.1" ||
          host === "0.0.0.0" ||
          host === "::1" ||
          host.startsWith("169.254.") ||
          host.startsWith("10.") ||
          host.startsWith("192.168.") ||
          host === "metadata.google.internal" ||
          host === "instance-data"
        ) {
          return false;
        }
        // Disallow 172.16.0.0 - 172.31.255.255
        const match172 = host.match(/^172\.(\d+)\./);
        if (match172) {
          const secondOctet = parseInt(match172[1], 10);
          if (secondOctet >= 16 && secondOctet <= 31) return false;
        }
        return true;
      } catch {
        return false;
      }
    }, "Live URL cannot point to internal, localhost, or cloud metadata addresses (SSRF protection)")
    .optional()
    .or(z.literal("")),
  description: z
    .string()
    .trim()
    .max(2000, "Description must be under 2000 characters")
    .optional()
    .or(z.literal("")),
});

export type SubmissionInput = z.infer<typeof submissionSchema>;
